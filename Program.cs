using System.Data;
using System.IO.Compression;
using System.Text;
using System.Xml.Linq;
using MySqlConnector;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(o => o.Limits.MaxRequestBodySize = 60L * 1024 * 1024);
builder.Services.AddProblemDetails();
var app = builder.Build();
app.UseExceptionHandler();
app.UseDefaultFiles();
app.UseStaticFiles();
app.Use(async (ctx, next) =>
{
    ctx.Response.Headers.XContentTypeOptions = "nosniff";
    ctx.Response.Headers.XFrameOptions = "SAMEORIGIN";
    ctx.Response.Headers.ContentSecurityPolicy = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'self'";
    await next();
});
var connectionString = builder.Configuration.GetConnectionString("Anka")
    ?? Environment.GetEnvironmentVariable("ANKA_MYSQL_CONNECTION");
if (string.IsNullOrWhiteSpace(connectionString))
    throw new InvalidOperationException("Configure ConnectionStrings:Anka or ANKA_MYSQL_CONNECTION.");
var storage = Path.GetFullPath(builder.Configuration["StoragePath"] ?? Path.Combine(app.Environment.ContentRootPath, "App_Data", "epubs"));
Directory.CreateDirectory(storage);
await using (var db = new MySqlConnection(connectionString))
{
    await db.OpenAsync();
    await using var create = new MySqlCommand("""
        CREATE TABLE IF NOT EXISTS books (
          id CHAR(36) CHARACTER SET ascii COLLATE ascii_general_ci NOT NULL PRIMARY KEY,
          title VARCHAR(500) NOT NULL,
          author VARCHAR(300) NOT NULL,
          language VARCHAR(32) NOT NULL,
          original_script VARCHAR(24) NOT NULL,
          filename VARCHAR(255) NOT NULL,
          bytes BIGINT NOT NULL,
          created_utc DATETIME(6) NOT NULL,
          INDEX ix_books_title (title(160))
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """, db);
    await create.ExecuteNonQueryAsync();
}
app.MapGet("/api/health", () => Results.Ok(new { status = "ok", app = "Anka", version = "phase1" }));
app.MapGet("/api/books", async () =>
{
    var list = new List<object>();
    await using var db = new MySqlConnection(connectionString);
    await db.OpenAsync();
    await using var cmd = new MySqlCommand("SELECT id,title,author,language,original_script,bytes,created_utc FROM books ORDER BY created_utc DESC", db);
    await using var reader = await cmd.ExecuteReaderAsync();
    while (await reader.ReadAsync())
        list.Add(new { id=reader.GetString(0), title=reader.GetString(1), author=reader.GetString(2),
            language=reader.GetString(3), script=reader.GetString(4), bytes=reader.GetInt64(5), uploaded=reader.GetDateTime(6) });
    return Results.Ok(list);
});
app.MapGet("/api/books/{id:guid}/file", async (Guid id) =>
{
    await using var db = new MySqlConnection(connectionString);
    await db.OpenAsync();
    await using var cmd = new MySqlCommand("SELECT filename FROM books WHERE id=@id", db);
    cmd.Parameters.AddWithValue("@id", id.ToString());
    var filename = await cmd.ExecuteScalarAsync() as string;
    if (filename is null) return Results.NotFound();
    var file = Path.Combine(storage, filename);
    return File.Exists(file) ? Results.File(file, "application/epub+zip", enableRangeProcessing:true) : Results.NotFound();
});
app.MapPost("/api/books", async (HttpRequest request) =>
{
    if (!request.HasFormContentType) return Results.BadRequest(new { error="multipart/form-data required" });
    var form = await request.ReadFormAsync();
    var upload = form.Files.GetFile("file");
    if (upload is null || upload.Length == 0 || upload.Length > 50L * 1024 * 1024)
        return Results.BadRequest(new { error="EPUB file must be between 1 byte and 50 MB" });
    if (!Path.GetExtension(upload.FileName).Equals(".epub", StringComparison.OrdinalIgnoreCase))
        return Results.BadRequest(new { error="Only .epub files are accepted" });
    var id=Guid.NewGuid();
    var name=id.ToString("N")+".epub";
    var path=Path.Combine(storage,name);
    await using (var target=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.None))
        await upload.CopyToAsync(target);
    try
    {
        using var zip=ZipFile.OpenRead(path);
        if(zip.Entries.Count > 15000 || zip.Entries.Sum(e => e.Length) > 200L*1024*1024)
            throw new InvalidDataException("EPUB expands beyond safe limits");
        var mimetype=zip.GetEntry("mimetype");
        if(mimetype is null) throw new InvalidDataException("Missing EPUB mimetype");
        using(var stream=mimetype.Open())
        using(var rdr=new StreamReader(stream,Encoding.ASCII))
            if((await rdr.ReadToEndAsync()).Trim()!="application/epub+zip") throw new InvalidDataException("Invalid EPUB mimetype");
        var container=zip.GetEntry("META-INF/container.xml") ?? throw new InvalidDataException("Missing EPUB container");
        XDocument containerXml;
        using(var s=container.Open()) containerXml=XDocument.Load(s);
        var opfName=containerXml.Descendants().FirstOrDefault(x=>x.Name.LocalName=="rootfile")?.Attribute("full-path")?.Value;
        if(string.IsNullOrEmpty(opfName) || opfName.StartsWith('/') || opfName.Contains("..") || opfName.Contains('\\'))
            throw new InvalidDataException("Invalid EPUB package path");
        var opf=zip.GetEntry(opfName) ?? throw new InvalidDataException("Missing EPUB package");
        XDocument package;
        using(var s=opf.Open()) package=XDocument.Load(s);
        string meta(string element) => package.Descendants().FirstOrDefault(x=>x.Name.LocalName==element)?.Value.Trim() ?? "";
        string first(string key, string fallback) =>
            (form[key].ToString().Trim() is string value && value.Length > 0) ? value : fallback;
        var title=first("title",meta("title"));
        var author=first("author",meta("creator"));
        var language=first("language",meta("language"));
        var script=first("script","auto");
        if(string.IsNullOrWhiteSpace(title)) title=Path.GetFileNameWithoutExtension(upload.FileName);
        if(title.Length>500 || author.Length>300 || language.Length>32 || script.Length>24)
            return RemoveAndFail(path, "Metadata field is too long");
        await using var db=new MySqlConnection(connectionString);
        await db.OpenAsync();
        await using var cmd=new MySqlCommand("""
            INSERT INTO books (id,title,author,language,original_script,filename,bytes,created_utc)
            VALUES (@id,@title,@author,@language,@script,@filename,@bytes,UTC_TIMESTAMP(6))
            """,db);
        cmd.Parameters.AddWithValue("@id",id.ToString());
        cmd.Parameters.AddWithValue("@title",title);
        cmd.Parameters.AddWithValue("@author",author);
        cmd.Parameters.AddWithValue("@language",language);
        cmd.Parameters.AddWithValue("@script",script);
        cmd.Parameters.AddWithValue("@filename",name);
        cmd.Parameters.AddWithValue("@bytes",upload.Length);
        await cmd.ExecuteNonQueryAsync();
        return Results.Created($"/api/books/{id}/file",new { id,title,author,language,script });
    }
    catch(InvalidDataException ex) { return RemoveAndFail(path,ex.Message); }
    catch(System.Xml.XmlException) { return RemoveAndFail(path,"Malformed EPUB XML"); }
    catch { File.Delete(path); throw; }
}).DisableAntiforgery();
app.Run();

static IResult RemoveAndFail(string path,string error)
{
    if(File.Exists(path)) File.Delete(path);
    return Results.BadRequest(new { error });
}
