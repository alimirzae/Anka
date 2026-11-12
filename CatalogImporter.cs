using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;

namespace Anka;

public sealed class CatalogImporter(
    IWebHostEnvironment env,
    IHttpClientFactory httpFactory,
    ILogger<CatalogImporter> logger)
{
    private readonly SemaphoreSlim gate = new(1,1);
    private string DatabasePath => Path.Combine(env.ContentRootPath, "App_Data", "anka.db");
    private string StoragePath => Path.Combine(env.ContentRootPath, "App_Data", "epubs");

    public static Guid BookId(CatalogBook item) =>
        new(MD5.HashData(Encoding.UTF8.GetBytes("ANKA public-domain catalog " + item.Slug)));

    public async Task<Guid> ImportAsync(CatalogBook item, CancellationToken token = default)
    {
        await gate.WaitAsync(token);
        try
        {
            var id = BookId(item);
            var filename = id.ToString("N") + ".epub";
            Directory.CreateDirectory(StoragePath);
            var target = Path.Combine(StoragePath, filename);
            if (File.Exists(target) && await DatabaseHasBook(id, token)) return id;

            // Download the authentic Turkish original from the explicitly allowlisted Wikisource page.
            var client = httpFactory.CreateClient("wikisource");
            var pageTitle = Uri.UnescapeDataString(new Uri(item.SourceUrl).AbsolutePath["/wiki/".Length..]);
            var url = "https://tr.wikisource.org/w/api.php?action=parse&format=json&formatversion=2&prop=text&page=" +
                Uri.EscapeDataString(pageTitle);
            using var response = await client.GetAsync(url, token);
            response.EnsureSuccessStatusCode();
            await using var stream = await response.Content.ReadAsStreamAsync(token);
            using var document = await JsonDocument.ParseAsync(stream, cancellationToken:token);
            var html = document.RootElement.GetProperty("parse").GetProperty("text").GetString() ?? "";
            var paragraphs = Regex.Matches(html, @"<p\b[^>]*>(.*?)</p>",
                RegexOptions.IgnoreCase | RegexOptions.Singleline, TimeSpan.FromSeconds(5))
                .Select(x => x.Groups[1].Value)
                .Select(x => Regex.Replace(x, @"<sup\b[^>]*>.*?</sup>", "", RegexOptions.IgnoreCase|RegexOptions.Singleline))
                .Select(x => Regex.Replace(x, @"<[^>]+>", " "))
                .Select(WebUtility.HtmlDecode)
                .Select(x => Regex.Replace(x, @"\s+", " ").Trim())
                .Where(x => x.Length >= 15 && !x.Contains("Vikikaynak", StringComparison.OrdinalIgnoreCase))
                .ToList();
            if (paragraphs.Count < 4 || paragraphs.Sum(x => x.Length) < 600)
                throw new InvalidDataException($"Wikisource extraction returned too little text for {item.Title}.");

            var temp = target + ".tmp";
            try
            {
                BuildEpub(temp, item, paragraphs);
                File.Move(temp, target, overwrite:true);
            }
            finally { if (File.Exists(temp)) File.Delete(temp); }

            var cs = new SqliteConnectionStringBuilder { DataSource=DatabasePath }.ToString();
            await using var db = new SqliteConnection(cs);
            await db.OpenAsync(token);
            await using var command = db.CreateCommand();
            command.CommandText = """
                INSERT OR REPLACE INTO books
                    (id,title,author,language,original_script,filename,bytes,created_utc)
                VALUES (@id,@title,@author,'tr','Latin',@filename,@bytes,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                """;
            command.Parameters.AddWithValue("@id",id.ToString());
            command.Parameters.AddWithValue("@title",item.Title);
            command.Parameters.AddWithValue("@author",item.Author);
            command.Parameters.AddWithValue("@filename",filename);
            command.Parameters.AddWithValue("@bytes",new FileInfo(target).Length);
            await command.ExecuteNonQueryAsync(token);
            return id;
        }
        finally { gate.Release(); }
    }

    private async Task<bool> DatabaseHasBook(Guid id, CancellationToken ct)
    {
        await using var db = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource=DatabasePath }.ToString());
        await db.OpenAsync(ct);
        await using var cmd = db.CreateCommand();
        cmd.CommandText="SELECT EXISTS(SELECT 1 FROM books WHERE id=@id)";
        cmd.Parameters.AddWithValue("@id",id.ToString());
        return Convert.ToInt32(await cmd.ExecuteScalarAsync(ct)) == 1;
    }

    private static void BuildEpub(string path,CatalogBook item,IReadOnlyList<string> paragraphs)
    {
        static string Escape(string s) => System.Security.SecurityElement.Escape(s) ?? "";
        using var file=File.Create(path);
        using var zip=new ZipArchive(file,ZipArchiveMode.Create);
        void Add(string name,string text,CompressionLevel compression=CompressionLevel.Optimal)
        {
            var entry=zip.CreateEntry(name,compression);
            using var writer=new StreamWriter(entry.Open(),new UTF8Encoding(false));
            writer.Write(text);
        }
        Add("mimetype","application/epub+zip",CompressionLevel.NoCompression);
        Add("META-INF/container.xml","""<?xml version="1.0" encoding="utf-8"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""");
        var body=string.Join("\n",paragraphs.Select(p=>"<p>"+Escape(p)+"</p>"));
        Add("EPUB/chapter.xhtml",$"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="tr"><head><title>{Escape(item.Title)}</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body>
<h1>{Escape(item.Title)}</h1><p class="byline">{Escape(item.Author)}</p>{body}
<p class="source">Kaynak: {Escape(item.SourceUrl)} · Vikikaynak · Kamu malı eser</p>
</body></html>""");
        Add("EPUB/style.css","body{font-family:serif;line-height:1.85;padding:1em}h1{text-align:center}.byline,.source{text-align:center;color:#777}p{text-align:justify;margin-bottom:1.1em}");
        Add("EPUB/nav.xhtml",$"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>İçindekiler</title></head><body><nav epub:type="toc" id="toc"><h1>İçindekiler</h1><ol><li><a href="chapter.xhtml">{Escape(item.Title)}</a></li></ol></nav></body></html>""");
        Add("EPUB/package.opf",$"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id" xml:lang="tr">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="pub-id">urn:uuid:{BookId(item)}</dc:identifier><dc:title>{Escape(item.Title)}</dc:title><dc:creator>{Escape(item.Author)}</dc:creator><dc:language>tr</dc:language></metadata>
<manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="style" href="style.css" media-type="text/css"/></manifest>
<spine><itemref idref="chapter"/></spine></package>""");
    }
}

public sealed class CatalogSeedWorker(CatalogImporter importer, ILogger<CatalogSeedWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken token)
    {
        // Import is best-effort. A Wikisource outage never prevents Anka from starting.
        await Task.Delay(TimeSpan.FromSeconds(5), token);
        foreach(var item in SampleCatalog.Items)
        {
            if(token.IsCancellationRequested)break;
            try { await importer.ImportAsync(item,token); }
            catch(OperationCanceledException) when(token.IsCancellationRequested){ break; }
            catch(Exception ex){ logger.LogWarning(ex,"Cannot import sample catalog book {Book}",item.Title); }
        }
    }
}
