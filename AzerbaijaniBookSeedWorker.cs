using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Data.Sqlite;

namespace Anka;

/// <summary>
/// Imports public-domain original Azerbaijani works from Azerbaijani Wikisource
/// and an explicitly marked machine-transliterated Arabic-script reading edition.
/// Transliteration is not a translation or a proofread scholarly edition.
/// </summary>
public sealed class AzerbaijaniBookSeedWorker(
    IWebHostEnvironment environment,
    IHttpClientFactory clients,
    ILogger<AzerbaijaniBookSeedWorker> logger) : BackgroundService
{
    private static readonly (string Slug, string Title, string Author)[] Works =
    [
        ("Uşaq_və_buz", "Uşaq və buz", "Mirzə Ələkbər Sabir"),
        ("Uşaq_və_pul", "Uşaq və pul", "Mirzə Ələkbər Sabir")
    ];

    public static Guid? OtherScript(Guid id)
    {
        foreach (var work in Works)
        {
            if (Id(work.Slug, "az-Latn") == id) return Id(work.Slug, "az-Arab");
            if (Id(work.Slug, "az-Arab") == id) return Id(work.Slug, "az-Latn");
        }
        return null;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        await Task.Delay(TimeSpan.FromSeconds(8), stoppingToken);
        foreach (var (slug, title, author) in Works)
        {
            if (stoppingToken.IsCancellationRequested) break;
            try
            {
                // Fetching source only when needed ensures restart is safe and offline
                // operation keeps existing copies.
                var latinId = Id(slug, "az-Latn");
                var arabId = Id(slug, "az-Arab");
                if (await IsReady(latinId, stoppingToken) && await IsReady(arabId, stoppingToken))
                    continue;

                var http = clients.CreateClient("wikisource");
                using var response = await http.GetAsync(
                    "https://az.wikisource.org/w/api.php?action=parse&format=json&formatversion=2&prop=text&page=" +
                    Uri.EscapeDataString(slug), stoppingToken);
                response.EnsureSuccessStatusCode();
                await using var stream = await response.Content.ReadAsStreamAsync(stoppingToken);
                using var json = await JsonDocument.ParseAsync(stream, cancellationToken: stoppingToken);
                var html = json.RootElement.GetProperty("parse").GetProperty("text").GetString() ?? "";
                var text = Regex.Replace(html, @"<sup\b[^>]*>.*?</sup>", "",
                    RegexOptions.IgnoreCase | RegexOptions.Singleline, TimeSpan.FromSeconds(5));
                // MediaWiki poem markup can use <p>, <div class="poem">, and <br>.
                // Remove page furniture before extracting the text blocks.
                text = Regex.Replace(text, @"<div\b[^>]*class\s*=\s*[""'][^""']*(?:mw-references|printfooter|catlinks)[^""']*[""'][^>]*>.*?</div>",
                    "", RegexOptions.IgnoreCase | RegexOptions.Singleline, TimeSpan.FromSeconds(5));
                var poem = Regex.Match(text, @"<div\b[^>]*class\s*=\s*[""'][^""']*poem[^""']*[""'][^>]*>(.*?)</div>",
                    RegexOptions.IgnoreCase | RegexOptions.Singleline, TimeSpan.FromSeconds(5));
                var sourceHtml = poem.Success ? poem.Groups[1].Value : text;
                var candidates = Regex.Matches(sourceHtml, @"<(?:p|dd|div)\b[^>]*>(.*?)</(?:p|dd|div)>",
                    RegexOptions.IgnoreCase | RegexOptions.Singleline, TimeSpan.FromSeconds(5))
                    .Select(m => m.Groups[1].Value)
                    .Select(t => Regex.Replace(t, @"<br\s*/?>", "\n", RegexOptions.IgnoreCase))
                    .Select(t => WebUtility.HtmlDecode(Regex.Replace(t, @"<[^>]+>", " ")))
                    .Select(t => Regex.Replace(t, @"[ \t]+", " ").Trim())
                    .Where(t => t.Length >= 25 && !t.Contains("Vikimənbə", StringComparison.OrdinalIgnoreCase))
                    .ToList();
                var verses = poem.Success
                    ? WebUtility.HtmlDecode(Regex.Replace(
                        Regex.Replace(sourceHtml, @"<br\s*/?>", "\n", RegexOptions.IgnoreCase),
                        @"<[^>]+>", " ")).Trim()
                    : candidates.OrderByDescending(t => t.Length).FirstOrDefault();
                if (verses is null || verses.Length < 100)
                    throw new InvalidDataException("No substantive Azerbaijani text at source " + slug);

                // Keep source text and transliteration in distinct books with distinct
                // permanent IDs so bookmarks and language metadata stay independent.
                await Persist(slug, title, author, "az-Latn", verses, stoppingToken);
                await Persist(slug, title + " — عرب الفباسی (آوانویسی ماشینی)",
                    author, "az-Arab", AzerbaijaniScript.ToArabic(verses), stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception ex)
            {
                logger.LogWarning(ex, "Could not seed Azerbaijani original {Title}", title);
            }
        }
    }

    private static Guid Id(string slug, string language) =>
        new(MD5.HashData(Encoding.UTF8.GetBytes("ANKA AZ Wikisource " + slug + " " + language)));

    private string DataDir => Path.Combine(environment.ContentRootPath, "App_Data");

    private async Task<bool> IsReady(Guid id, CancellationToken ct)
    {
        var path = Path.Combine(DataDir, "epubs", id.ToString("N") + ".epub");
        if (!File.Exists(path)) return false;
        await using var db = new SqliteConnection(new SqliteConnectionStringBuilder {
            DataSource = Path.Combine(DataDir, "anka.db") }.ToString());
        await db.OpenAsync(ct);
        await using var cmd = db.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM books WHERE id=@id";
        cmd.Parameters.AddWithValue("@id", id.ToString());
        return Convert.ToInt32(await cmd.ExecuteScalarAsync(ct)) > 0;
    }

    private async Task Persist(string slug, string title, string author, string language,
        string content, CancellationToken ct)
    {
        var id = Id(slug, language);
        if (await IsReady(id, ct)) return;
        var folder = Path.Combine(DataDir, "epubs");
        Directory.CreateDirectory(folder);
        var filename = id.ToString("N") + ".epub";
        var path = Path.Combine(folder, filename);
        var tmp = path + ".tmp";
        try
        {
            CreateEpub(tmp, id, title, author, language, content,
                "https://az.wikisource.org/wiki/" + slug);
            File.Move(tmp, path, true);
            await using var db = new SqliteConnection(new SqliteConnectionStringBuilder {
                DataSource = Path.Combine(DataDir, "anka.db") }.ToString());
            await db.OpenAsync(ct);
            await using var cmd = db.CreateCommand();
            cmd.CommandText = """
                INSERT OR REPLACE INTO books
                  (id,title,author,language,original_script,filename,bytes,created_utc)
                VALUES (@id,@title,@author,@lang,@script,@filename,@bytes,strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                """;
            cmd.Parameters.AddWithValue("@id", id.ToString());
            cmd.Parameters.AddWithValue("@title", title);
            cmd.Parameters.AddWithValue("@author", author);
            cmd.Parameters.AddWithValue("@lang", language);
            cmd.Parameters.AddWithValue("@script", language == "az-Arab" ? "Arabic (machine transliteration)" : "Latin");
            cmd.Parameters.AddWithValue("@filename", filename);
            cmd.Parameters.AddWithValue("@bytes", new FileInfo(path).Length);
            await cmd.ExecuteNonQueryAsync(ct);
        }
        finally { if (File.Exists(tmp)) File.Delete(tmp); }
    }

    private static void CreateEpub(string path, Guid id, string title, string author,
        string lang, string text, string source)
    {
        static string X(string value) => System.Security.SecurityElement.Escape(value) ?? "";
        using var fs = File.Create(path);
        using var zip = new ZipArchive(fs, ZipArchiveMode.Create);
        void Add(string pathInZip, string body, CompressionLevel level = CompressionLevel.Optimal)
        {
            var entry = zip.CreateEntry(pathInZip, level);
            using var writer = new StreamWriter(entry.Open(), new UTF8Encoding(false));
            writer.Write(body);
        }
        Add("mimetype", "application/epub+zip", CompressionLevel.NoCompression);
        Add("META-INF/container.xml", """<?xml version="1.0" encoding="utf-8"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""");
        var paragraphs = string.Join("\n", text.Split('\n', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)
            .Select(line => "<p>" + X(line) + "</p>"));
        var note = lang == "az-Arab"
            ? "Avtomatik ərəb qrafikasına köçürmə — redaktə olunmayıb (آوانویسی ماشینی، نیازمند بازبینی)."
            : "Orijinal Azərbaycan mətnidir.";
        Add("EPUB/chapter.xhtml",
            $"""<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}" dir="{(lang == "az-Arab" ? "rtl" : "ltr")}"><head><title>{X(title)}</title></head><body><h1>{X(title)}</h1><p>{X(author)}</p><p>{X(note)}</p>{paragraphs}<p>{X(source)}</p></body></html>""");
        Add("EPUB/nav.xhtml", $"""<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">{X(title)}</a></li></ol></nav></body></html>""");
        Add("EPUB/package.opf", $"""<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="bookid">urn:uuid:{id}</dc:identifier><dc:title>{X(title)}</dc:title><dc:creator>{X(author)}</dc:creator><dc:language>{lang}</dc:language><dc:source>{X(source)}</dc:source></metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine><itemref idref="chapter"/></spine></package>""");
    }
}

/// <summary>Approximate spelling converter for review, not a validated orthography.</summary>
internal static class AzerbaijaniScript
{
    private static readonly Dictionary<char, string> Map = new()
    {
        ['a']="ا", ['b']="ب", ['c']="ج", ['ç']="چ", ['d']="د", ['e']="ئ",
        ['ə']="ه", ['f']="ف", ['g']="گ", ['ğ']="غ", ['h']="ه", ['x']="خ",
        ['ı']="ی", ['i']="ی", ['j']="ژ", ['k']="ک", ['q']="ق", ['l']="ل",
        ['m']="م", ['n']="ن", ['o']="و", ['ö']="ؤ", ['p']="پ", ['r']="ر",
        ['s']="س", ['ş']="ش", ['t']="ت", ['u']="و", ['ü']="ۆ", ['v']="و",
        ['y']="ی", ['z']="ز"
    };
    public static string ToArabic(string latin)
    {
        var output = new StringBuilder();
        foreach (char ch in latin)
        {
            if (Map.TryGetValue(char.ToLowerInvariant(ch), out string? part)) output.Append(part);
            else output.Append(ch);
        }
        return output.ToString();
    }
}
