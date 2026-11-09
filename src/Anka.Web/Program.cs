using System.Text.Encodings.Web;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddRazorPages();
var app = builder.Build();

if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/error");
    app.UseHsts();
}
app.UseHttpsRedirection();
app.UseStaticFiles();
app.UseRouting();
app.MapRazorPages();

app.MapGet("/api/editions/locales", () => Results.Ok(new[]
{
    new { tag = "az-Arab", label = "آذربایجان تورکجه‌سی — عرب الفباسی", direction = "rtl" },
    new { tag = "az-Latn", label = "Azərbaycan türkcəsi — Latın", direction = "ltr" },
    new { tag = "tr-Latn", label = "Türkiye Türkçesi", direction = "ltr" }
}));

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));
app.MapGet("/error", () => Results.Problem("An unexpected error occurred."));

app.Run();
