using System.Security.Claims;
using System.IO.Compression;
using System.Text;
using System.Xml;
using System.Xml.Linq;
using Microsoft.Data.Sqlite;

namespace Anka;

public sealed record ReadingPage(int Number, IReadOnlyList<string> Paragraphs, string Chapter);
public sealed record ReadingDocument(string Title, string Author, string Language, IReadOnlyList<ReadingPage> Pages);

/// <summary>
/// Server-side EPUB text reader: no external JavaScript CDN and no HTML from the EPUB
/// is ever inserted into the DOM. All book text is encoded by Blazor.
/// </summary>
public sealed class EpubReadingService(IWebHostEnvironment environment, ILogger<EpubReadingService> log, AnkaAccountService accounts, IHttpContextAccessor httpContextAccessor)
{
    public async Task<ReadingDocument> OpenAsync(Guid id, CancellationToken ct = default, string? authenticatedUserId = null)
    {
        var viewer=authenticatedUserId ?? httpContextAccessor.HttpContext?.User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
        if(!await accounts.CanReadAsync(viewer,id.ToString()))throw new UnauthorizedAccessException("Access to this edition is not granted.");
        var cs = new SqliteConnectionStringBuilder {
            DataSource = Path.Combine(environment.ContentRootPath, "App_Data", "anka.db"),
            Mode = SqliteOpenMode.ReadWrite
        }.ToString();
        string filename, title, author, language;
        await using (var db = new SqliteConnection(cs))
        {
            await db.OpenAsync(ct);
            await using var cmd = db.CreateCommand();
            cmd.CommandText = """
                SELECT filename,title,author,language FROM books b WHERE id=@id
                AND NOT EXISTS(SELECT 1 FROM anka_book_moderation m WHERE m.book_id=b.id AND m.state!='approved')
                """;
            cmd.Parameters.AddWithValue("@id", id.ToString());
            await using var reader = await cmd.ExecuteReaderAsync(ct);
            if (!await reader.ReadAsync(ct)) throw new FileNotFoundException("Book is not in the library.");
            filename=reader.GetString(0);
            title=reader.GetString(1);
            author=reader.GetString(2);
            language=reader.GetString(3);
        }

        // Never trust a path from the database to escape the dedicated EPUB directory.
        if (Path.GetFileName(filename) != filename ||
            !filename.EndsWith(".epub", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Invalid EPUB filename.");

        var path = Path.Combine(environment.ContentRootPath, "App_Data", "epubs", filename);
        if (!File.Exists(path)) throw new FileNotFoundException("EPUB file is missing.");
        using var zip = ZipFile.OpenRead(path);
        if (zip.Entries.Count > 15000) throw new InvalidDataException("EPUB has too many entries.");

        var container=zip.GetEntry("META-INF/container.xml") ?? throw new InvalidDataException("EPUB container missing.");
        var containerXml=LoadXml(container);
        var opfPath=containerXml.Descendants().FirstOrDefault(x=>x.Name.LocalName=="rootfile")?.Attribute("full-path")?.Value
            ?? throw new InvalidDataException("EPUB package missing.");
        opfPath=SafeArchivePath("",opfPath);
        var opf=zip.GetEntry(opfPath) ?? throw new InvalidDataException("EPUB package cannot be opened.");
        var package=LoadXml(opf);
        var baseDir=opfPath.Contains('/') ? opfPath[..(opfPath.LastIndexOf('/')+1)] : "";
        var items=package.Descendants().Where(x=>x.Name.LocalName=="item")
            .Select(x=>new {Id=(string?)x.Attribute("id"),Href=(string?)x.Attribute("href"),Media=(string?)x.Attribute("media-type")})
            .Where(x=>!string.IsNullOrEmpty(x.Id) && !string.IsNullOrEmpty(x.Href))
            .ToDictionary(x=>x.Id!,x=>x, StringComparer.Ordinal);
        var pages=new List<ReadingPage>();
        var pending=new List<string>();
        var count=0;
        var chapterTitle=title;
        const int pageTarget=1200;
        void Flush()
        {
            if(pending.Count==0)return;
            pages.Add(new ReadingPage(pages.Count+1,pending.ToList(),chapterTitle));
            pending.Clear();count=0;
        }
        foreach(var spine in package.Descendants().Where(x=>x.Name.LocalName=="itemref"))
        {
            ct.ThrowIfCancellationRequested();
            var idref=(string?)spine.Attribute("idref");
            if(idref is null || !items.TryGetValue(idref,out var item) ||
                item.Media is not ("application/xhtml+xml" or "text/html")) continue;
            var chapterPath=SafeArchivePath(baseDir,item.Href!);
            var entry=zip.GetEntry(chapterPath);
            if(entry is null || entry.Length>12*1024*1024) continue;
            XDocument chapter;
            try { chapter=LoadXml(entry); }
            catch(XmlException e) { log.LogWarning(e,"Unreadable EPUB chapter {Path}",chapterPath); continue; }

            var body=chapter.Descendants().FirstOrDefault(x=>x.Name.LocalName=="body");
            if(body is null)continue;
            var firstHeading=body.Descendants().FirstOrDefault(x => x.Name.LocalName is "h1" or "h2" or "h3");
            var fallbackHeading=firstHeading is null ? $"Section {pages.Count+1}" : string.Join(" ",firstHeading.DescendantNodes().OfType<XText>().Select(x=>x.Value)).Trim();
            if (!string.IsNullOrWhiteSpace(fallbackHeading)) chapterTitle=fallbackHeading.Length>110 ? fallbackHeading[..110] : fallbackHeading;
            var blocks=body.Descendants().Where(x=>x.Name.LocalName is "h1" or "h2" or "h3" or "p" or "li" or "blockquote").ToList();
            if(blocks.Count==0)blocks.Add(body);
            foreach(var block in blocks)
            {
                var text=string.Join(" ",block.DescendantNodes().OfType<XText>().Select(x=>x.Value));
                text=string.Join(" ",text.Split((char[]?)null,StringSplitOptions.RemoveEmptyEntries)).Trim();
                if(text.Length==0)continue;
                // Split very long paragraphs at a word boundary to keep page sizes usable on mobile.
                for(var position=0;position<text.Length;)
                {
                    var remaining=text.Length-position;
                    var take=Math.Min(remaining,pageTarget);
                    if(take<remaining)
                    {
                        var lastSpace=text.LastIndexOf(' ',position+take-1,take);
                        if(lastSpace>position+pageTarget/2)take=lastSpace-position;
                    }
                    var part=text.Substring(position,take).Trim();
                    position+=take;
                    while(position<text.Length && text[position]==' ')position++;
                    if(part.Length==0)continue;
                    if(count+part.Length>pageTarget && pending.Count>0)Flush();
                    pending.Add(part);count+=part.Length;
                }
            }
            Flush(); // Start a new visible page for the next chapter.
        }
        Flush();
        if(pages.Count==0)throw new InvalidDataException("EPUB contains no readable text chapters.");
        return new ReadingDocument(title,author,language,pages);
    }

    private static XDocument LoadXml(ZipArchiveEntry entry)
    {
        using var stream=entry.Open();
        using var reader=XmlReader.Create(stream,new XmlReaderSettings{
            DtdProcessing=DtdProcessing.Prohibit,XmlResolver=null,MaxCharactersInDocument=15_000_000
        });
        return XDocument.Load(reader);
    }

    private static string SafeArchivePath(string root,string relative)
    {
        relative=Uri.UnescapeDataString(relative.Split('#')[0]).Replace('\\','/');
        if(relative.StartsWith('/') || relative.Contains(':'))throw new InvalidDataException("Invalid EPUB chapter path.");
        var parts=new List<string>();
        foreach(var p in (root+relative).Split('/'))
        {
            if(p=="" || p==".")continue;
            if(p==".."){if(parts.Count==0)throw new InvalidDataException("Unsafe EPUB path.");parts.RemoveAt(parts.Count-1);}
            else parts.Add(p);
        }
        return string.Join("/",parts);
    }
}