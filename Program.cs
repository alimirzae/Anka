using System.IO.Compression;
using System.Text;
using System.Xml.Linq;
using Anka.Components;
using MySqlConnector;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(o => o.Limits.MaxRequestBodySize = 60L * 1024 * 1024);
builder.Services.AddProblemDetails();
builder.Services.AddHttpClient("local", client => client.BaseAddress = new Uri(builder.Configuration["InternalBaseUrl"] ?? "http://127.0.0.1:5000/"));
builder.Services.AddRazorComponents().AddInteractiveServerComponents();
var connectionString = builder.Configuration.GetConnectionString("Anka")
    ?? Environment.GetEnvironmentVariable("ANKA_MYSQL_CONNECTION");
if (string.IsNullOrWhiteSpace(connectionString))
    throw new InvalidOperationException("Configure ConnectionStrings:Anka or ANKA_MYSQL_CONNECTION.");
var app = builder.Build();
app.UseExceptionHandler();
app.UseStaticFiles();
app.UseAntiforgery();
var storage = Path.GetFullPath(builder.Configuration["StoragePath"] ?? Path.Combine(app.Environment.ContentRootPath, "App_Data", "epubs"));
Directory.CreateDirectory(storage);
await using (var db = new MySqlConnection(connectionString))
{
    await db.OpenAsync();
    await using var cmd = new MySqlCommand("""
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
    await cmd.ExecuteNonQueryAsync();
}
app.MapGet("/api/health", () => Results.Ok(new { status = "ok", app = "Anka", framework = "Blazor Server" }));
app.MapGet("/api/books", async () =>
{
    var books = new List<BookListItem>();
    await using var db = new MySqlConnection(connectionString);
    await db.OpenAsync();
    await using var cmd = new MySqlCommand("SELECT id,title,author,language,original_script,bytes FROM books ORDER BY created_utc DESC", db);
    await using var r = await cmd.ExecuteReaderAsync();
    while (await r.ReadAsync())
        books.Add(new BookListItem(r.GetString(0), r.GetString(1), r.GetString(2), r.GetString(3), r.GetString(4), r.GetInt64(5)));
    return Results.Ok(books);
});
app.MapGet("/api/books/{id:guid}/file", async (Guid id) =>
{
    await using var db = new MySqlConnection(connectionString);
    await db.OpenAsync();
    await using var cmd = new MySqlCommand("SELECT filename FROM books WHERE id=@id", db);
    cmd.Parameters.AddWithValue("@id", id.ToString());
    var name = await cmd.ExecuteScalarAsync() as string;
    if (name is null) return Results.NotFound();
    var path = Path.Combine(storage, name);
    return File.Exists(path) ? Results.File(path, "application/epub+zip", enableRangeProcessing: true) : Results.NotFound();
});
app.MapPost("/api/books", async (HttpRequest request) =>
{
    if (!request.HasFormContentType) return Results.BadRequest(new { error = "multipart/form-data required" });
    var form = await request.ReadFormAsync();
    var file = form.Files.GetFile("file");
    if (file is null || file.Length == 0 || file.Length > 50L * 1024 * 1024 ||
        !Path.GetExtension(file.FileName).Equals(".epub", StringComparison.OrdinalIgnoreCase))
        return Results.BadRequest(new { error = "Only EPUB up to 50MB supported." });
    var id = Guid.NewGuid();
    var name = id.ToString("N") + ".epub";
    var path = Path.Combine(storage, name);
    await using (var dest = File.Create(path)) await file.CopyToAsync(dest);
    try
    {
        using var archive = ZipFile.OpenRead(path);
        if (archive.Entries.Count > 15000 || archive.Entries.Sum(e => e.Length) > 200L * 1024 * 1024)
            throw new InvalidDataException("EPUB exceeds limits.");
        var mime = archive.GetEntry("mimetype") ?? throw new InvalidDataException("EPUB mimetype missing.");
        using (var sr = new StreamReader(mime.Open(), Encoding.ASCII))
            if ((await sr.ReadToEndAsync()).Trim() != "application/epub+zip")
                throw new InvalidDataException("Invalid EPUB mimetype.");
        var container = archive.GetEntry("META-INF/container.xml") ?? throw new InvalidDataException("Container missing.");
        XDocument xml;
        using (var stream = container.Open()) xml = XDocument.Load(stream);
        var opfPath = xml.Descendants().FirstOrDefault(x => x.Name.LocalName == "rootfile")?.Attribute("full-path")?.Value;
        if (string.IsNullOrEmpty(opfPath) || opfPath.StartsWith('/') || opfPath.Contains("..") || opfPath.Contains('\\'))
            throw new InvalidDataException("Invalid package path.");
        var opf = archive.GetEntry(opfPath) ?? throw new InvalidDataException("Package missing.");
        XDocument package;
        using (var stream = opf.Open()) package = XDocument.Load(stream);
        string meta(string tag) => package.Descendants().FirstOrDefault(x => x.Name.LocalName == tag)?.Value.Trim() ?? "";
        string value(string key, string fallback) => string.IsNullOrWhiteSpace(form[key]) ? fallback : form[key].ToString().Trim();
        var title = value("title", meta("title"));
        var author = value("author", meta("creator"));
        var language = value("language", meta("language"));
        if (string.IsNullOrWhiteSpace(title)) title = Path.GetFileNameWithoutExtension(file.FileName);
        if (title.Length > 500 || author.Length > 300 || language.Length > 32)
            throw new InvalidDataException("Metadata too long.");
        await using var db = new MySqlConnection(connectionString);
        await db.OpenAsync();
        await using var cmd = new MySqlCommand("""
          INSERT INTO books (id,title,author,language,original_script,filename,bytes,created_utc)
          VALUES (@id,@title,@author,@language,'auto',@file,@bytes,UTC_TIMESTAMP(6))
        """, db);
        cmd.Parameters.AddWithValue("@id", id.ToString());
        cmd.Parameters.AddWithValue("@title", title);
        cmd.Parameters.AddWithValue("@author", author);
        cmd.Parameters.AddWithValue("@language", language);
        cmd.Parameters.AddWithValue("@file", name);
        cmd.Parameters.AddWithValue("@bytes", file.Length);
        await cmd.ExecuteNonQueryAsync();
        return Results.Created($"/api/books/{id}/file", new { id, title });
    }
    catch (InvalidDataException e) { File.Delete(path); return Results.BadRequest(new { error = e.Message }); }
    catch (System.Xml.XmlException) { File.Delete(path); return Results.BadRequest(new { error = "Malformed EPUB XML." }); }
    catch { File.Delete(path); throw; }
}).DisableAntiforgery();
app.MapRazorComponents<App>().AddInteractiveServerRenderMode();
app.Run();

public record BookListItem(string Id, string Title, string Author, string Language, string Script, long Bytes);
