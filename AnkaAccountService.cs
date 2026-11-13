using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.Data.Sqlite;

namespace Anka;

/// <summary>Durable local accounts with password hashing, role claims and safe defaults.</summary>
public sealed class AnkaAccountService(IWebHostEnvironment env)
{
    private string Connection => new SqliteConnectionStringBuilder {
        DataSource=Path.Combine(env.ContentRootPath,"App_Data","anka.db"),
        Mode=SqliteOpenMode.ReadWriteCreate,DefaultTimeout=30
    }.ToString();

    public async Task EnsureCreatedAsync(CancellationToken ct=default)
    {
        await using var db=new SqliteConnection(Connection);
        await db.OpenAsync(ct);
        await using var cmd=db.CreateCommand();
        cmd.CommandText="""
            CREATE TABLE IF NOT EXISTS anka_users(
              id TEXT PRIMARY KEY,
              email TEXT NOT NULL UNIQUE COLLATE NOCASE,
              display_name TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              role TEXT NOT NULL DEFAULT 'Reader',
              disabled INTEGER NOT NULL DEFAULT 0,
              created_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS anka_user_shelves(
              user_id TEXT NOT NULL,
              book_id TEXT NOT NULL,
              added_utc TEXT NOT NULL,
              PRIMARY KEY(user_id,book_id),
              FOREIGN KEY(user_id) REFERENCES anka_users(id)
            );
            CREATE TABLE IF NOT EXISTS anka_works(
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              author TEXT NOT NULL,
              description TEXT NOT NULL DEFAULT '',
              category TEXT NOT NULL DEFAULT 'General',
              created_utc TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS anka_editions(
              book_id TEXT PRIMARY KEY,
              work_id TEXT NOT NULL,
              language TEXT NOT NULL,
              script TEXT NOT NULL,
              translator TEXT NOT NULL DEFAULT '',
              content_status TEXT NOT NULL DEFAULT 'complete',
              publisher_name TEXT NOT NULL DEFAULT '',
              price_minor INTEGER NOT NULL DEFAULT 0,
              currency TEXT NOT NULL DEFAULT 'IRR',
              FOREIGN KEY(work_id) REFERENCES anka_works(id)
            );
            CREATE TABLE IF NOT EXISTS anka_publisher_requests(
              user_id TEXT PRIMARY KEY,
              statement TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'pending',
              requested_utc TEXT NOT NULL,
              reviewed_utc TEXT,
              FOREIGN KEY(user_id) REFERENCES anka_users(id)
            );
            CREATE TABLE IF NOT EXISTS anka_book_moderation(
              book_id TEXT PRIMARY KEY,
              uploader_id TEXT NOT NULL,
              rights_statement TEXT NOT NULL,
              state TEXT NOT NULL DEFAULT 'pending',
              reviewed_by TEXT,
              created_utc TEXT NOT NULL,
              reviewed_utc TEXT
            );
            CREATE TABLE IF NOT EXISTS anka_publisher_submissions(
              id TEXT PRIMARY KEY,
              user_id TEXT NOT NULL,
              book_id TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              rights_statement TEXT NOT NULL,
              submitted_utc TEXT NOT NULL,
              reviewed_utc TEXT,
              FOREIGN KEY(user_id) REFERENCES anka_users(id)
            );
            """;
        await cmd.ExecuteNonQueryAsync(ct);
        // Additive migration: preserve the existing books table and every stored EPUB.
        cmd.CommandText="""
          INSERT OR IGNORE INTO anka_works(id,title,author,created_utc)
            SELECT id,title,author,created_utc FROM books;
          INSERT OR IGNORE INTO anka_editions(book_id,work_id,language,script,content_status)
            SELECT id,id,language,original_script,
              CASE WHEN title LIKE '%آوانویسی ماشینی%' THEN 'unreviewed'
                ELSE 'complete' END
            FROM books;
          """;
        await cmd.ExecuteNonQueryAsync(ct);
    }

    private static string Hash(string password)
    {
        var salt=RandomNumberGenerator.GetBytes(16);
        var hash=Rfc2898DeriveBytes.Pbkdf2(password,salt,240_000,HashAlgorithmName.SHA256,32);
        return "v1:"+Convert.ToBase64String(salt)+":"+Convert.ToBase64String(hash);
    }
    private static bool Verify(string password,string encoded)
    {
        var segments=encoded.Split(':');
        if(segments.Length!=3 || segments[0]!="v1")return false;
        try {
            var salt=Convert.FromBase64String(segments[1]);
            var expected=Convert.FromBase64String(segments[2]);
            if(salt.Length!=16 || expected.Length!=32)return false;
            var actual=Rfc2898DeriveBytes.Pbkdf2(password,salt,240_000,HashAlgorithmName.SHA256,32);
            return CryptographicOperations.FixedTimeEquals(actual,expected);
        }catch(FormatException){return false;}
    }
    public async Task<(bool Success,string Error)> RegisterAsync(string email,string name,string password)
    {
        email=email.Trim().ToLowerInvariant();name=name.Trim();
        if(email.Length>254 || email.Length<5 || !System.Net.Mail.MailAddress.TryCreate(email,out var mail) || mail.Address!=email)
            return(false,"Valid email required.");
        if(name.Length<2 || name.Length>100 || password.Length<12 || password.Length>128)
            return(false,"Name must be 2–100 characters and password at least 12 characters.");
        await using var db=new SqliteConnection(Connection);
        await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="INSERT INTO anka_users(id,email,display_name,password_hash,role,created_utc) VALUES(@id,@email,@name,@hash,'Reader',strftime('%Y-%m-%dT%H:%M:%fZ','now'))";
        cmd.Parameters.AddWithValue("@id",Guid.NewGuid().ToString());
        cmd.Parameters.AddWithValue("@email",email);
        cmd.Parameters.AddWithValue("@name",name);
        cmd.Parameters.AddWithValue("@hash",Hash(password));
        try {await cmd.ExecuteNonQueryAsync();return(true,"");}
        catch(SqliteException ex) when(ex.SqliteErrorCode==19){return(false,"Account already exists.");}
    }
    public async Task<(string Id,string Name,string Role)?> AuthenticateAsync(string email,string password)
    {
        email=email.Trim().ToLowerInvariant();
        if(email.Length>254 || password.Length>128)return null;
        await using var db=new SqliteConnection(Connection);
        await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="SELECT id,display_name,role,password_hash FROM anka_users WHERE email=@email AND disabled=0";
        cmd.Parameters.AddWithValue("@email",email);
        await using var reader=await cmd.ExecuteReaderAsync();
        if(!await reader.ReadAsync())return null;
        string id=reader.GetString(0),name=reader.GetString(1),role=reader.GetString(2),hash=reader.GetString(3);
        return Verify(password,hash)?(id,name,role):null;
    }
    // Test-only credential lookup. The calling HTTP endpoint must be development AND loopback only.
    public async Task<(string Id,string Name,string Role)?> FindLocalTestAccountAsync(string email)
    {
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="SELECT id,display_name,role FROM anka_users WHERE email=@email AND disabled=0";
        cmd.Parameters.AddWithValue("@email",email.Trim().ToLowerInvariant());
        await using var r=await cmd.ExecuteReaderAsync();
        if(!await r.ReadAsync())return null;
        return(r.GetString(0),r.GetString(1),r.GetString(2));
    }
    public async Task<bool> MakePublisherAsync(string userId)
    {
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="UPDATE anka_users SET role='Publisher' WHERE id=@id AND role='Reader'";
        cmd.Parameters.AddWithValue("@id",userId);
        return await cmd.ExecuteNonQueryAsync()==1;
    }

    public async Task<IReadOnlyList<AnkaPublisherRequest>> PublisherRequestsAsync()
    {
        var result=new List<AnkaPublisherRequest>();
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="""
          SELECT r.user_id,u.display_name,u.email,r.statement,r.state
          FROM anka_publisher_requests r JOIN anka_users u ON u.id=r.user_id
          ORDER BY CASE r.state WHEN 'pending' THEN 0 ELSE 1 END,r.requested_utc DESC
          """;
        await using var reader=await cmd.ExecuteReaderAsync();
        while(await reader.ReadAsync())result.Add(new(reader.GetString(0),reader.GetString(1),reader.GetString(2),reader.GetString(3),reader.GetString(4)));
        return result;
    }
    public async Task<bool> RequestPublisherAsync(string userId,string statement)
    {
        statement=statement.Trim();
        if(statement.Length<12||statement.Length>1500)return false;
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="""
          INSERT INTO anka_publisher_requests(user_id,statement,state,requested_utc)
          VALUES(@id,@text,'pending',strftime('%Y-%m-%dT%H:%M:%fZ','now'))
          ON CONFLICT(user_id) DO UPDATE SET statement=excluded.statement,state='pending',
          requested_utc=excluded.requested_utc,reviewed_utc=NULL
          """;
        cmd.Parameters.AddWithValue("@id",userId);cmd.Parameters.AddWithValue("@text",statement);
        return await cmd.ExecuteNonQueryAsync()>0;
    }
    public async Task<bool> ReviewPublisherAsync(string userId,bool approve)
    {
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var transaction=await db.BeginTransactionAsync();
        await using var cmd=db.CreateCommand();cmd.Transaction=(SqliteTransaction)transaction;
        cmd.CommandText="UPDATE anka_publisher_requests SET state=@state,reviewed_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE user_id=@id AND state='pending'";
        cmd.Parameters.AddWithValue("@state",approve?"approved":"rejected");
        cmd.Parameters.AddWithValue("@id",userId);
        if(await cmd.ExecuteNonQueryAsync()!=1)return false;
        if(approve){
            cmd.CommandText="UPDATE anka_users SET role='Publisher' WHERE id=@id AND role='Reader'";
            await cmd.ExecuteNonQueryAsync();
        }
        await transaction.CommitAsync();
        return true;
    }
    public async Task<bool> IsCurrentRoleAsync(string userId,string role)
    {
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="SELECT COUNT(*) FROM anka_users WHERE id=@id AND role=@role AND disabled=0";
        cmd.Parameters.AddWithValue("@id",userId);cmd.Parameters.AddWithValue("@role",role);
        return Convert.ToInt32(await cmd.ExecuteScalarAsync())==1;
    }
    public async Task<bool> RecordBookSubmissionAsync(string bookId,string uploaderId,string rights)
    {
        if(rights.Trim().Length<12||rights.Length>2000)return false;
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="INSERT INTO anka_book_moderation(book_id,uploader_id,rights_statement,state,created_utc) VALUES(@id,@user,@rights,'pending',strftime('%Y-%m-%dT%H:%M:%fZ','now'))";
        cmd.Parameters.AddWithValue("@id",bookId);cmd.Parameters.AddWithValue("@user",uploaderId);cmd.Parameters.AddWithValue("@rights",rights.Trim());
        return await cmd.ExecuteNonQueryAsync()==1;
    }
    public async Task<IReadOnlyList<AnkaSubmission>> BookSubmissionsAsync()
    {
        var result=new List<AnkaSubmission>();
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="""
          SELECT m.book_id,b.title,m.rights_statement,m.state
          FROM anka_book_moderation m JOIN books b ON b.id=m.book_id
          ORDER BY CASE m.state WHEN 'pending' THEN 0 ELSE 1 END,m.created_utc DESC
          """;
        await using var r=await cmd.ExecuteReaderAsync();
        while(await r.ReadAsync())result.Add(new(r.GetString(0),r.GetString(1),r.GetString(2),r.GetString(3)));
        return result;
    }
    public async Task<IReadOnlyList<AnkaSubmission>> MyBookSubmissionsAsync(string userId)
    {
        var result=new List<AnkaSubmission>();
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="""
          SELECT m.book_id,b.title,m.rights_statement,m.state
          FROM anka_book_moderation m JOIN books b ON b.id=m.book_id
          WHERE m.uploader_id=@user
          ORDER BY m.created_utc DESC
          """;
        cmd.Parameters.AddWithValue("@user",userId);
        await using var r=await cmd.ExecuteReaderAsync();
        while(await r.ReadAsync())result.Add(new(r.GetString(0),r.GetString(1),r.GetString(2),r.GetString(3)));
        return result;
    }
    public async Task<bool> ReviewBookAsync(string bookId,string reviewerId,bool approve)
    {
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="UPDATE anka_book_moderation SET state=@state,reviewed_by=@reviewer,reviewed_utc=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE book_id=@id AND state='pending'";
        cmd.Parameters.AddWithValue("@id",bookId);cmd.Parameters.AddWithValue("@reviewer",reviewerId);
        cmd.Parameters.AddWithValue("@state",approve?"approved":"rejected");
        return await cmd.ExecuteNonQueryAsync()==1;
    }
    public async Task<bool> HasActiveAdminAsync()
    {
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="SELECT EXISTS(SELECT 1 FROM anka_users WHERE role='Admin' AND disabled=0)";
        return Convert.ToInt32(await cmd.ExecuteScalarAsync())!=0;
    }
    public async Task<bool> BootstrapAdminAsync(string userId)
    {
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="""
        UPDATE anka_users SET role='Admin'
        WHERE id=@id AND disabled=0
          AND NOT EXISTS(SELECT 1 FROM anka_users WHERE role='Admin' AND disabled=0)
        """;
        cmd.Parameters.AddWithValue("@id",userId);
        return await cmd.ExecuteNonQueryAsync()==1;
    }

    public async Task<IReadOnlyList<AnkaEditionInfo>> OtherEditionsAsync(string bookId)
    {
        var editions=new List<AnkaEditionInfo>();
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="""
          SELECT b.id,b.title,e.language,e.content_status,e.translator,e.publisher_name
          FROM anka_editions current
          JOIN anka_editions e ON e.work_id=current.work_id
          JOIN books b ON b.id=e.book_id
          WHERE current.book_id=@id AND
            NOT EXISTS(SELECT 1 FROM anka_book_moderation m
              WHERE m.book_id=b.id AND m.state!='approved')
          ORDER BY CASE e.language WHEN 'az-Arab' THEN 0 WHEN 'tr' THEN 1 WHEN 'az-Latn' THEN 2 ELSE 3 END
          """;
        cmd.Parameters.AddWithValue("@id",bookId);
        await using var r=await cmd.ExecuteReaderAsync();
        while(await r.ReadAsync())editions.Add(new(r.GetString(0),r.GetString(1),r.GetString(2),r.GetString(3),r.GetString(4),r.GetString(5)));
        return editions;
    }
    public async Task<bool> LinkEditionAsync(string bookId,string targetWorkId)
    {
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="""
          UPDATE anka_editions SET work_id=@work
          WHERE book_id=@book AND EXISTS(SELECT 1 FROM anka_works WHERE id=@work)
          """;
        cmd.Parameters.AddWithValue("@book",bookId);cmd.Parameters.AddWithValue("@work",targetWorkId);
        return await cmd.ExecuteNonQueryAsync()==1;
    }
    public async Task<IReadOnlyList<string>> ShelfAsync(string userId)
    {
        var result=new List<string>();
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="SELECT book_id FROM anka_user_shelves WHERE user_id=@user ORDER BY added_utc DESC";
        cmd.Parameters.AddWithValue("@user",userId);
        await using var r=await cmd.ExecuteReaderAsync();
        while(await r.ReadAsync())result.Add(r.GetString(0));
        return result;
    }
    public async Task AddToShelfAsync(string userId,string bookId)
    {
        await using var db=new SqliteConnection(Connection);await db.OpenAsync();
        await using var cmd=db.CreateCommand();
        cmd.CommandText="INSERT OR IGNORE INTO anka_user_shelves(user_id,book_id,added_utc) VALUES(@u,@b,strftime('%Y-%m-%dT%H:%M:%fZ','now'))";
        cmd.Parameters.AddWithValue("@u",userId);cmd.Parameters.AddWithValue("@b",bookId);
        await cmd.ExecuteNonQueryAsync();
    }
}

public sealed record AnkaPublisherRequest(string UserId,string Name,string Email,string Statement,string State);
public sealed record AnkaSubmission(string BookId,string Title,string Rights,string State);

public sealed record AnkaEditionInfo(string BookId,string Title,string Language,string ContentStatus,string Translator,string Publisher);
