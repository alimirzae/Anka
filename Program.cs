using Microsoft.AspNetCore.DataProtection;
using System.Security.Claims;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.RateLimiting;
using System.IO.Compression;
using System.Text;
using System.Xml.Linq;
using Anka.Components;
using Anka;
using Microsoft.Data.Sqlite;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(o => o.Limits.MaxRequestBodySize = 60L * 1024 * 1024);
builder.Services.AddProblemDetails();
builder.Services.AddRazorComponents().AddInteractiveServerComponents();
builder.Services.AddScoped<UiText>();
builder.Services.AddSingleton<AnkaAccountService>();
builder.Services.AddDataProtection().SetApplicationName("ANKA-Reader")
    .PersistKeysToFileSystem(new DirectoryInfo(Path.Combine(builder.Environment.ContentRootPath,"App_Data","keys")));
builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme)
    .AddCookie(options=>{
        options.Cookie.Name="Anka.Session";
        options.Cookie.HttpOnly=true;
        options.Cookie.SecurePolicy=CookieSecurePolicy.Always;
        options.Cookie.SameSite=SameSiteMode.Strict;
        options.ExpireTimeSpan=TimeSpan.FromDays(14);
        options.SlidingExpiration=true;
        options.Events.OnRedirectToLogin=context=>{
            if(context.Request.Path.StartsWithSegments("/api")) {
                context.Response.StatusCode=401;
                return Task.CompletedTask;
            }
            context.Response.Redirect("/account");
            return Task.CompletedTask;
        };
        options.Events.OnRedirectToAccessDenied=context=>{
            context.Response.StatusCode=403;
            return Task.CompletedTask;
        };
    });
builder.Services.AddAuthorization();
builder.Services.AddRateLimiter(options=>{
    options.RejectionStatusCode=429;
    options.AddPolicy("account",context=>System.Threading.RateLimiting.RateLimitPartition.GetFixedWindowLimiter(
        context.Connection.RemoteIpAddress?.ToString()??"unknown",
        _=>new System.Threading.RateLimiting.FixedWindowRateLimiterOptions{
            PermitLimit=8,Window=TimeSpan.FromMinutes(2),QueueLimit=0,AutoReplenishment=true
        }));
});
builder.Services.AddScoped<EpubReadingService>();
builder.Services.AddHttpClient("wikisource", client => {
    client.Timeout=TimeSpan.FromSeconds(35);
    client.DefaultRequestHeaders.UserAgent.ParseAdd("AnkaReader/1.0 (https://anka.iyashil.com/; public-domain book catalog)");
});
builder.Services.AddSingleton<CatalogImporter>();
builder.Services.AddHostedService<CatalogSeedWorker>();
builder.Services.AddHostedService<AzerbaijaniBookSeedWorker>();
Directory.CreateDirectory(Path.Combine(builder.Environment.ContentRootPath,"App_Data","keys"));
var app = builder.Build();
app.UseExceptionHandler();
app.UseStaticFiles();
app.UseAuthentication();
app.UseAuthorization();
app.UseRateLimiter();
app.UseAntiforgery();

// SQLite and uploaded EPUB files live outside wwwroot and survive IIS redeployments.
var dataDirectory = Path.Combine(app.Environment.ContentRootPath, "App_Data");
var storage = Path.Combine(dataDirectory, "epubs");
Directory.CreateDirectory(storage);
var databaseFile = Path.Combine(dataDirectory, "anka.db");
var connectionString = new SqliteConnectionStringBuilder
{
    DataSource = databaseFile,
    Mode = SqliteOpenMode.ReadWriteCreate,
    Pooling = true,
    DefaultTimeout = 30
}.ToString();
await using (var db = new SqliteConnection(connectionString))
{
    await db.OpenAsync();
    await using var cmd = db.CreateCommand();
    cmd.CommandText = """
        CREATE TABLE IF NOT EXISTS books (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            language TEXT NOT NULL,
            original_script TEXT NOT NULL,
            filename TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            created_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_books_title ON books(title);
        """;
    await cmd.ExecuteNonQueryAsync();
}

await app.Services.GetRequiredService<AnkaAccountService>().EnsureCreatedAsync();

static bool SameOrigin(HttpRequest request)
{
    var origin=request.Headers.Origin.ToString();
    if(!string.IsNullOrEmpty(origin)){
        return Uri.TryCreate(origin,UriKind.Absolute,out var uri) &&
            uri.Scheme==request.Scheme && uri.Authority.Equals(request.Host.Value,StringComparison.OrdinalIgnoreCase);
    }
    return request.Headers["Sec-Fetch-Site"].ToString()=="same-origin";
}
app.MapPost("/api/account/register",async (HttpContext context,AnkaAccountService accounts,AnkaCredentials input)=>{
    if(!SameOrigin(context.Request))return Results.StatusCode(403);
    var (ok,error)=await accounts.RegisterAsync(input.Email??"",input.Name??"",input.Password??"");
    return ok?Results.Ok(new{ok=true}):Results.BadRequest(new{error});
}).RequireRateLimiting("account");
app.MapPost("/api/account/login",async (HttpContext context,AnkaAccountService accounts,AnkaCredentials input)=>{
    if(!SameOrigin(context.Request))return Results.StatusCode(403);
    var account=await accounts.AuthenticateAsync(input.Email??"",input.Password??"");
    if(account is null)return Results.Json(new{error="Invalid credentials."},statusCode:401);
    var identity=new ClaimsIdentity(new[]{
        new Claim(ClaimTypes.NameIdentifier,account.Value.Id),
        new Claim(ClaimTypes.Name,account.Value.Name),
        new Claim(ClaimTypes.Role,account.Value.Role)
    },CookieAuthenticationDefaults.AuthenticationScheme);
    await context.SignInAsync(CookieAuthenticationDefaults.AuthenticationScheme,new ClaimsPrincipal(identity));
    return Results.Ok(new{ok=true,role=account.Value.Role});
}).RequireRateLimiting("account");
app.MapPost("/api/account/logout",async (HttpContext context)=>{
    if(!SameOrigin(context.Request))return Results.StatusCode(403);
    await context.SignOutAsync();
    return Results.Ok(new{ok=true});
}).RequireAuthorization();
app.MapGet("/api/account/me",(ClaimsPrincipal user)=>Results.Ok(new{
    authenticated=user.Identity?.IsAuthenticated==true,
    name=user.Identity?.Name,
    role=user.FindFirst(ClaimTypes.Role)?.Value
}));
app.MapGet("/api/me/shelf",async (ClaimsPrincipal user,AnkaAccountService accounts)=>{
    var id=user.FindFirst(ClaimTypes.NameIdentifier)?.Value;
    return id is null?Results.Unauthorized():Results.Ok(await accounts.ShelfAsync(id));
}).RequireAuthorization();
app.MapPost("/api/me/shelf/{bookId:guid}",async (Guid bookId,HttpContext context,AnkaAccountService accounts)=>{
    if(!SameOrigin(context.Request))return Results.StatusCode(403);
    var id=context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
    if(id is null)return Results.Unauthorized();
    await accounts.AddToShelfAsync(id,bookId.ToString());
    return Results.Ok(new{ok=true});
}).RequireAuthorization();

app.MapPost("/api/admin/bootstrap",async(HttpContext context,AnkaAccountService accounts)=>{
    if(!SameOrigin(context.Request))return Results.StatusCode(403);
    var secret=Environment.GetEnvironmentVariable("ANKA_ADMIN_SETUP_KEY");
    if(string.IsNullOrWhiteSpace(secret)||secret.Length<32)return Results.StatusCode(503);
    var provided=context.Request.Headers["X-Anka-Setup-Key"].ToString();
    if(secret.Length!=provided.Length||!CryptographicOperations.FixedTimeEquals(
        Encoding.UTF8.GetBytes(secret),Encoding.UTF8.GetBytes(provided)))return Results.StatusCode(403);
    var userId=context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
    if(userId is null)return Results.Unauthorized();
    return await accounts.BootstrapAdminAsync(userId)?Results.Ok(new{ok=true}):Results.BadRequest();
}).RequireAuthorization().RequireRateLimiting("account");
app.MapPost("/api/publisher/request",async(HttpContext context,AnkaAccountService accounts,AnkaRightsRequest request)=>{
    if(!SameOrigin(context.Request))return Results.StatusCode(403);
    var id=context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
    return id is not null&&await accounts.RequestPublisherAsync(id,request.Statement??"")?
        Results.Ok(new{ok=true}):Results.BadRequest(new{error="A statement of at least 12 characters is required."});
}).RequireAuthorization().RequireRateLimiting("account");
app.MapGet("/api/admin/publishers",async(AnkaAccountService accounts)=>Results.Ok(await accounts.PublisherRequestsAsync()))
    .RequireAuthorization(policy=>policy.RequireRole("Admin"));
app.MapPost("/api/admin/publishers/{id:guid}/review",async(Guid id,HttpContext context,AnkaAccountService accounts,AnkaReview review)=>{
    if(!SameOrigin(context.Request))return Results.StatusCode(403);
    var reviewer=context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
    if(reviewer is null||!await accounts.IsCurrentRoleAsync(reviewer,"Admin"))return Results.Forbid();
    return await accounts.ReviewPublisherAsync(id.ToString(),review.Approve)?Results.Ok(new{ok=true}):Results.NotFound();
}).RequireAuthorization(policy=>policy.RequireRole("Admin"));
app.MapGet("/api/publisher/my-submissions",async(HttpContext context,AnkaAccountService accounts)=>{
    var userId=context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
    if(userId is null)return Results.Unauthorized();
    return Results.Ok(await accounts.MyBookSubmissionsAsync(userId));
}).RequireAuthorization(policy=>policy.RequireRole("Publisher","Admin"));
app.MapGet("/api/admin/submissions",async(AnkaAccountService accounts)=>Results.Ok(await accounts.BookSubmissionsAsync()))
    .RequireAuthorization(policy=>policy.RequireRole("Admin"));
app.MapPost("/api/admin/submissions/{id:guid}/review",async(Guid id,HttpContext context,AnkaAccountService accounts,AnkaReview review)=>{
    if(!SameOrigin(context.Request))return Results.StatusCode(403);
    var reviewer=context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
    if(reviewer is null||!await accounts.IsCurrentRoleAsync(reviewer,"Admin"))return Results.Forbid();
    return await accounts.ReviewBookAsync(id.ToString(),reviewer,review.Approve)?Results.Ok(new{ok=true}):Results.NotFound();
}).RequireAuthorization(policy=>policy.RequireRole("Admin"));
app.MapGet("/api/books/{id:guid}/editions",async(Guid id,AnkaAccountService accounts)=>
    Results.Ok(await accounts.OtherEditionsAsync(id.ToString())));
app.MapPost("/api/admin/editions/{id:guid}/link",async(Guid id,HttpContext context,AnkaAccountService accounts,AnkaEditionLink request)=>{
    if(!SameOrigin(context.Request))return Results.StatusCode(403);
    var reviewer=context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
    if(reviewer is null||!await accounts.IsCurrentRoleAsync(reviewer,"Admin"))return Results.Forbid();
    if(!Guid.TryParse(request.WorkId,out var target))return Results.BadRequest();
    return await accounts.LinkEditionAsync(id.ToString(),target.ToString())?Results.Ok(new{ok=true}):Results.NotFound();
}).RequireAuthorization(policy=>policy.RequireRole("Admin"));
app.MapGet("/api/health", () => Results.Ok(new { status = "ok", app = "Anka", framework = "Blazor Server" }));
app.MapGet("/api/catalog/status", async () =>
{
    var imported = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    await using var db = new SqliteConnection(connectionString);
    await db.OpenAsync();
    await using var command = db.CreateCommand();
    command.CommandText = "SELECT id FROM books";
    await using var r = await command.ExecuteReaderAsync();
    while (await r.ReadAsync()) imported.Add(r.GetString(0));
    var items = SampleCatalog.Items.Select(x => new {
        x.Slug, x.Title,
        imported = imported.Contains(CatalogImporter.BookId(x).ToString()) &&
                   File.Exists(Path.Combine(storage, CatalogImporter.BookId(x).ToString("N")+".epub")),
        source = x.SourceUrl
    }).ToList();
    return Results.Ok(new { total=items.Count, ready=items.Count(x=>x.imported), books=items });
});
app.MapGet("/api/books/{id:guid}/reading-status", async (Guid id, EpubReadingService reader) =>
{
    try
    {
        var book=await reader.OpenAsync(id);
        return Results.Ok(new { id, title=book.Title, pages=book.Pages.Count, characters=book.Pages.Sum(p=>p.Paragraphs.Sum(t=>t.Length)), firstPage=book.Pages[0].Paragraphs.Count });
    }
    catch(FileNotFoundException){ return Results.NotFound(new {error="Book not found"}); }
    catch(InvalidDataException){ return Results.Problem("EPUB cannot be parsed",statusCode:422); }
});
app.MapGet("/api/books", async () =>
{
    var books = new List<BookListItem>();
    await using var db = new SqliteConnection(connectionString);
    await db.OpenAsync();
    await using var cmd = new SqliteCommand("""
        SELECT b.id,b.title,b.author,b.language,b.original_script,b.bytes,COALESCE(w.category,'General')
        FROM books b LEFT JOIN anka_editions e ON e.book_id=b.id
        LEFT JOIN anka_works w ON w.id=e.work_id
        WHERE NOT EXISTS (SELECT 1 FROM anka_book_moderation m WHERE m.book_id=b.id AND m.state!='approved')
        ORDER BY b.created_utc DESC
        """, db);
    await using var r = await cmd.ExecuteReaderAsync();
    while (await r.ReadAsync())
        books.Add(new BookListItem(r.GetString(0), r.GetString(1), r.GetString(2), r.GetString(3), r.GetString(4), r.GetInt64(5),r.GetString(6)));
    return Results.Ok(books);
});
app.MapGet("/api/books/{id:guid}/file", async (Guid id,HttpContext context) =>
{
    await using var db = new SqliteConnection(connectionString);
    await db.OpenAsync();
    await using var cmd = new SqliteCommand("SELECT filename FROM books WHERE id=@id", db);
    cmd.Parameters.AddWithValue("@id", id.ToString());
    var name = await cmd.ExecuteScalarAsync() as string;
    if (name is null) return Results.NotFound();
    var path = Path.Combine(storage, name);
    return File.Exists(path) ? Results.File(path, "application/epub+zip", enableRangeProcessing: true) : Results.NotFound();
});
app.MapPost("/api/books", async (HttpRequest request,AnkaAccountService accounts) =>
{
    if (!SameOrigin(request)) return Results.StatusCode(403);
    var uploader=request.HttpContext.User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
    if(uploader is null || !(await accounts.IsCurrentRoleAsync(uploader,"Publisher")||await accounts.IsCurrentRoleAsync(uploader,"Admin")))return Results.StatusCode(403);
    var rightsDeclaration=request.Headers["X-Anka-Rights"].ToString().Trim();
    if(rightsDeclaration.Length<12||rightsDeclaration.Length>2000)return Results.BadRequest(new {error="A publishing-rights declaration is required."});
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
        var category = value("category","General");
        var description = value("description","");
        var translator = value("translator","");
        var publisherName = value("publisherName","");
        if (string.IsNullOrWhiteSpace(title)) title = Path.GetFileNameWithoutExtension(file.FileName);
        if (!new[]{"General","Literature","Poetry","History","Children","Science"}.Contains(category))
            throw new InvalidDataException("Invalid book category.");
        if (description.Length>2000||translator.Length>150||publisherName.Length>150)
            throw new InvalidDataException("Metadata too long.");
        if (title.Length > 500 || author.Length > 300 || language.Length > 32)
            throw new InvalidDataException("Metadata too long.");
        await using var db = new SqliteConnection(connectionString);
        await db.OpenAsync();
        await using var transaction = (SqliteTransaction)await db.BeginTransactionAsync();
        await using var cmd = new SqliteCommand("""
          INSERT INTO books (id,title,author,language,original_script,filename,bytes,created_utc)
          VALUES (@id,@title,@author,@language,'auto',@file,@bytes,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        """, db,transaction);
        cmd.Parameters.AddWithValue("@id", id.ToString());
        cmd.Parameters.AddWithValue("@title", title);
        cmd.Parameters.AddWithValue("@author", author);
        cmd.Parameters.AddWithValue("@language", language);
        cmd.Parameters.AddWithValue("@file", name);
        cmd.Parameters.AddWithValue("@bytes", file.Length);
        await cmd.ExecuteNonQueryAsync();
        await using var rightsCmd = new SqliteCommand("""
          INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,state,created_utc)
          VALUES(@id,@uploader,@rights,'pending',strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        """,db,transaction);
        rightsCmd.Parameters.AddWithValue("@id",id.ToString());
        rightsCmd.Parameters.AddWithValue("@uploader",uploader);
        rightsCmd.Parameters.AddWithValue("@rights",rightsDeclaration);
        await rightsCmd.ExecuteNonQueryAsync();
        await using var workCmd = new SqliteCommand("""
          INSERT INTO anka_works(id,title,author,description,category,created_utc)
          VALUES(@id,@title,@author,@description,@category,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        """,db,transaction);
        workCmd.Parameters.AddWithValue("@id",id.ToString());
        workCmd.Parameters.AddWithValue("@title",title);
        workCmd.Parameters.AddWithValue("@author",author);
        workCmd.Parameters.AddWithValue("@description",description);
        workCmd.Parameters.AddWithValue("@category",category);
        await workCmd.ExecuteNonQueryAsync();
        await using var editionCmd = new SqliteCommand("""
          INSERT INTO anka_editions(book_id,work_id,language,script,content_status,translator,publisher_name)
          VALUES(@id,@id,@language,@script,'unreviewed',@translator,@publisher)
        """,db,transaction);
        editionCmd.Parameters.AddWithValue("@id",id.ToString());
        editionCmd.Parameters.AddWithValue("@language",language);
        editionCmd.Parameters.AddWithValue("@translator",translator);
        editionCmd.Parameters.AddWithValue("@publisher",publisherName);
        editionCmd.Parameters.AddWithValue("@script",language is "az-Arab" or "fa" ? "Arabic" : "Latin");
        await editionCmd.ExecuteNonQueryAsync();
        await transaction.CommitAsync();
        return Results.Created($"/api/books/{id}/file", new { id, title, state="pending" });
    }
    catch (InvalidDataException e) { File.Delete(path); return Results.BadRequest(new { error = e.Message }); }
    catch (System.Xml.XmlException) { File.Delete(path); return Results.BadRequest(new { error = "Malformed EPUB XML." }); }
    catch { File.Delete(path); throw; }
}).RequireAuthorization(policy=>policy.RequireRole("Publisher","Admin")).DisableAntiforgery();
app.MapRazorComponents<App>().AddInteractiveServerRenderMode();
app.Run();

public record AnkaRightsRequest(string? Statement);
public record AnkaReview(bool Approve);
public record AnkaEditionLink(string? WorkId);
public record AnkaCredentials(string? Email,string? Password,string? Name);
public record BookListItem(string Id, string Title, string Author, string Language, string Script, long Bytes, string Category="General");
