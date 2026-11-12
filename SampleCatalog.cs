namespace Anka;

public sealed record CatalogBook(
    string Slug, string Title, string Author, string Category, string Summary,
    string SourceUrl, string Accent, string PreviewTr, string PreviewAz, string PreviewArabic);

public static class SampleCatalog
{
    // These are original ANKA test translations of opening excerpts, NOT complete translated editions.
    public static readonly IReadOnlyList<CatalogBook> Items = new List<CatalogBook>
    {
        new("kasagi","Kaşağı","Ömer Seyfettin","داستان کوتاه",
            "داستانی درباره دو برادر، اسب‌ها و پیامد تلخ یک دروغ.",
            "https://tr.wikisource.org/wiki/Ka%C5%9Fa%C4%9F%C4%B1","#4b6979",
            "Ahırın avlusunda oynarken derenin sesini işitirdik. Annem İstanbul'a gitmişti. Kardeşim Hasan'la atların yanından ayrılmıyorduk.",
            "Tövlənin həyətində oynayanda dərənin səsini eşidirdik. Anam İstanbula getmişdi. Qardaşım Həsənlə atların yanından ayrılmırdıq.",
            "طؤوله‌نین حیه‌تینده اوینایاندا دره‌نین سسینی ائشیدیردیک. آنام ایستانبولا گئتمیشدی. قارداشیم حسن‌له آتلارین یانیندان آیریلمیردیق."),
        new("falaka","Falaka","Ömer Seyfettin","خاطرات",
            "روایتی از مدرسه قدیمی و تنبیه دانش‌آموزان.",
            "https://tr.wikisource.org/wiki/Falaka","#9a583b",
            "Her sabah mektebe giderdik. Mektebin bahçesinde büyük ağaçlar vardı. Hocanın yaşlı eşeği de orada beklerdi.",
            "Hər səhər məktəbə gedirdik. Məktəbin həyətində böyük ağaclar vardı. Müəllimin qoca eşşəyi də orada gözləyərdi.",
            "هر سحر مکتبه گئدیردیک. مکتبین حیه‌تینده بؤیوک آغاجلار واردی. معلمین قوجا ائششه‌یی ده اورادا گؤزله‌یردی."),
        new("pembe-incili-kaftan","Pembe İncili Kaftan","Ömer Seyfettin","تاریخی",
            "داستان عزت‌نفس یک سفیر در دربار شاه.",
            "https://tr.wikisource.org/wiki/Pembe_%C4%B0ncili_Kaftan","#745380",
            "Divan bugün sessizdi. Vezirler cesur bir elçi arıyordu. Muhsin Çelebi, devletin şerefini korumaya kararlıydı.",
            "Divan bu gün sakit idi. Vəzirlər cəsur bir elçi axtarırdılar. Möhsün Çələbi dövlətin şərəfini qorumağa qərarlı idi.",
            "دیوان بو گون ساکیت ایدی. وزیرلر جسور بیر ائلچی آختاریردیلار. محسن چلبی دؤولتین شرفینی قوروماگا قرارلی ایدی."),
        new("diyet","Diyet","Ömer Seyfettin","اخلاقی",
            "روایت آهنگری مستقل که با غرورش زندگی می‌کند.",
            "https://tr.wikisource.org/wiki/Diyet","#58684a",
            "Koca Ali karanlık dükkânında demir döverdi. Yaptığı kılıçlar her yerde tanınırdı. Kimseden yardım istemezdi.",
            "Qoca Əli qaranlıq dükanında dəmir döyərdi. Hazırladığı qılınclar hər yerdə tanınırdı. Heç kimdən kömək istəməzdi.",
            "قوجا علی قارانلیق دوکانین‌دا دمیر دؤیه‌ردی. حاضیرلادیغی قیلینجلار هر یئرده تانینیردی. هئچ کیمدن کؤمک ایسته‌مزدی."),
        new("yalniz-efe","Yalnız Efe","Ömer Seyfettin","ماجراجویی",
            "افسانه زنی شجاع که در کوهستان مقابل ستم می‌ایستد.",
            "https://tr.wikisource.org/wiki/Yaln%C4%B1z_Efe","#326e6b",
            "Sabahtan beri dağ yollarında yürüyorduk. Yağmur yağıyordu. Rehberim bana Yalnız Efe'nin hikâyesini anlatmaya başladı.",
            "Səhərdən bəri dağ yolları ilə gedirdik. Yağış yağırdı. Bələdçim mənə Yalnız Əfənin hekayəsini danışmağa başladı.",
            "سحردن بری داغ یوللاری ایله گئدیردیک. یاغیش یاغیردی. بلدچیم منه یالنیز افه‌نین حکایه‌سینی دانیشماغا باشلادی.")
    };
    public static CatalogBook? Find(string slug) => Items.FirstOrDefault(x => x.Slug == slug);
}
