using MySqlConnector;

namespace Anka;

/// <summary>
/// Sole database connection source. ConnectionStrings__AnkaMySql is required;
/// production never silently creates another SQLite database.
/// </summary>
public sealed class AnkaDatabase(IConfiguration configuration, IWebHostEnvironment environment)
{
    private string ConnectionString => configuration.GetConnectionString("AnkaMySql") is { Length: > 0 } cs
        ? cs : throw new InvalidOperationException(
            "Missing ConnectionStrings:AnkaMySql. Configure MySQL and import the verified SQLite snapshot before enabling ANKA.");

    public MySqlConnection CreateConnection() => new(ConnectionString);

    public async Task EnsureCreatedAsync(CancellationToken ct = default)
    {
        await using var db = CreateConnection();
        await db.OpenAsync(ct);
        var schemaFile = Path.Combine(environment.ContentRootPath, "sql", "mysql-schema.sql");
        var schema = await File.ReadAllTextAsync(schemaFile, ct);
        foreach (var statement in schema.Split(';', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
        {
            if (!statement.Contains("CREATE TABLE", StringComparison.OrdinalIgnoreCase)) continue;
            await using var cmd = db.CreateCommand();
            cmd.CommandText = statement;
            await cmd.ExecuteNonQueryAsync(ct);
        }
        // Only backfill legacy catalog records when their work/edition rows are missing.
        await using var works = db.CreateCommand();
        works.CommandText = """
            INSERT IGNORE INTO anka_works(id,title,author,description,category,created_utc)
            SELECT id,title,author,'','General',created_utc FROM books
            """;
        await works.ExecuteNonQueryAsync(ct);
        await using var editions = db.CreateCommand();
        editions.CommandText = """
            INSERT IGNORE INTO anka_editions(book_id,work_id,language,script,content_status)
            SELECT id,id,language,original_script,
              CASE WHEN title LIKE '%آوانویسی ماشینی%' THEN 'unreviewed'
                   ELSE 'complete' END FROM books
            """;
        await editions.ExecuteNonQueryAsync(ct);
    }
}
