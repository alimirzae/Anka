using System.Collections.ObjectModel;

namespace Anka;

/// <summary>Four UI languages; book-content language is selected separately in the reader.</summary>
public sealed class UiText
{
    public const string DefaultLanguage = "fa";
    public string Language { get; private set; } = DefaultLanguage;
    public string Direction => Language is "fa" or "az-Arab" ? "rtl" : "ltr";
    public event Action? Changed;

    private static readonly Dictionary<string, string[]> Messages = new(StringComparer.OrdinalIgnoreCase)
    {
        // Persian, Turkish, Azerbaijani Latin, Azerbaijani Arabic
        ["brandSub"] = ["کتابخانه دیجیتال", "Dijital Kütüphane", "Rəqəmsal kitabxana", "دیجیتال کیتابخانا"],
        ["banner"] = ["آنکا، خانه کتاب و فرهنگ", "Anka, kitapların ve kültürün evi", "Anka, kitab və mədəniyyət evi", "آنکا، کیتاب و مدنیت ائوی"],
        ["home"] = ["خانه", "Ana sayfa", "Ana səhifə", "آنا صفحه"],
        ["discover"] = ["کشف کتاب‌ها", "Kitapları keşfet", "Kitabları kəşf et", "کیتابلاری کشف ائت"],
        ["freeBooks"] = ["کتاب‌های رایگان", "Ücretsiz kitaplar", "Pulsuz kitablar", "پولسوز کیتابلار"],
        ["myLibrary"] = ["کتابخانه من", "Kütüphanem", "Kitabxanam", "کیتابخانام"],
        ["addBook"] = ["افزودن کتاب", "Kitap ekle", "Kitab əlavə et", "کیتاب آرتیر"],
        ["search"] = ["جست‌وجوی کتاب", "Kitap ara", "Kitab axtar", "کیتاب آختار"],
        ["theme"] = ["تغییر حالت روشن و تاریک", "Açık / koyu görünüm", "Açıq / tünd görünüş", "آچیق / قارانلیق گؤرونوش"],
        ["uiLanguage"] = ["زبان برنامه", "Uygulama dili", "Tətbiqin dili", "پروقرامین دیلی"],
        ["tagline"] = ["کتاب، زبان و فرهنگ در یک خانه.", "Kitap, dil ve kültür bir arada.", "Kitab, dil və mədəniyyət bir yerdə.", "کیتاب، دیل و مدنیت بیر یئرده."],
        ["footerAbout"] = ["درباره این نسخه", "Bu sürüm hakkında", "Bu versiya haqqında", "بو نسخه حاقیندا"],
        ["noAccount"] = ["نسخه آزمایشی — بدون حساب کاربری", "Deneme sürümü — hesap gerekmez", "Sınaq versiyası — hesab lazım deyil", "سیناق نسخه‌سی — حساب لازیم دئییل"],
        ["heroHeading"] = ["دنیای کتاب، همیشه همراه شما.", "Kitapların dünyası her zaman yanınızda.", "Kitab dünyası həmişə yanınızda.", "کیتاب دونیاسی همیشه یانینیزدا."],
        ["heroDescription"] = ["ادبیات کلاسیک ترکی را کشف کنید و با موبایل یا رایانه مطالعه کنید.", "Türk klasiklerini keşfedin; telefonda veya bilgisayarda okuyun.", "Türk klassiklərini kəşf edin; telefonda və ya kompüterdə oxuyun.", "تورک کلاسیک‌لرینی کشف ائدین؛ تلفون یا کمپیوترله اوخویون."],
        ["explore"] = ["کاوش کتاب‌ها", "Kitaplara göz at", "Kitablara bax", "کیتابلارا باخ"],
        ["noLogin"] = ["بدون نیاز به ثبت‌نام", "Kayıt gerekmez", "Qeydiyyatsız", "قئیدیاتسیز"],
        ["onlineRead"] = ["مطالعه آنلاین EPUB", "Çevrimiçi EPUB okuma", "Onlayn EPUB oxu", "آنلاین EPUB اوخو"],
        ["personalShelf"] = ["کتابخانه شخصی", "Kişisel kütüphane", "Şəxsi kitabxana", "شخصی کیتابخانا"],
        ["personalShelfDetail"] = ["کتاب‌های EPUB شما", "EPUB kitaplarınız", "EPUB kitablarınız", "EPUB کیتابلارینیز"],
        ["dayNight"] = ["مطالعه روز و شب", "Gündüz / gece okuma", "Gündüz / gecə oxu", "گوندوز / گئجه اوخو"],
        ["dayNightDetail"] = ["اندازه قلم و ظاهر", "Yazı boyutu ve tema", "Şrift ölçüsü və mövzu", "یازی اؤلچوسو و تم"],
        ["threeScripts"] = ["سه حالت مطالعه", "Üç okuma seçeneği", "Üç oxu seçimi", "اوچ اوخو سئچیمی"],
        ["threeScriptsDetail"] = ["ترکی، آذربایجانی لاتین و عربی", "Türkçe ve iki Azerbaycan yazısı", "Türkcə və iki Azərbaycan yazısı", "تورکجه و ایکی آذربایجان یازیسی"],
        ["responsive"] = ["در همه دستگاه‌ها", "Tüm cihazlarda", "Bütün cihazlarda", "بوتون جیحازلارد‌ا"],
        ["responsiveDetail"] = ["موبایل و دسکتاپ", "Telefon ve bilgisayar", "Telefon və kompüter", "تلفون و کمپیوتر"],
        ["editorChoice"] = ["منتخب سردبیر", "Editörün seçimi", "Redaktorun seçimi", "رداکتورون سئچیمی"],
        ["turkishClassics"] = ["ادبیات کلاسیک ترکیه", "Türk edebiyatı klasikleri", "Türkiyə ədəbiyyatı klassikləri", "تورکیه ادبیاتی کلاسیک‌لری"],
        ["fiveStories"] = ["پنج داستان از عمر سیف‌الدین با جلد اختصاصی", "Ömer Seyfettin'den beş öykü", "Ömər Seyfəddindən beş hekayə", "عمر سیف‌الدین‌دن بئش حکایه"],
        ["featured"] = ["منتخب · رایگان", "Seçkin · Ücretsiz", "Seçilmiş · Pulsuz", "سئچیلمیش · پولسوز"],
        ["all"] = ["همه", "Tümü", "Hamısı", "هامیسی"],
        ["shortStory"] = ["داستان کوتاه", "Kısa öykü", "Qısa hekayə", "قیسا حکایه"],
        ["historical"] = ["تاریخی", "Tarihî", "Tarixi", "تاریخی"],
        ["adventure"] = ["ماجراجویی", "Macera", "Macəra", "ماجرا"],
        ["viewBook"] = ["مشاهده کتاب", "Kitabı incele", "Kitaba bax", "کیتابا باخ"],
        ["previewThree"] = ["پیش‌نمایش سه‌زبانه", "Üç dilli önizleme", "Üç dilli önbaxış", "اوچ دیللی اؤن باخیش"],
        ["sourceNote"] = ["آذربایجانی فعلاً تنها نمونه ترجمه است؛ نسخه کامل، ترکی استانبولی است.", "Azerbaycanca yalnızca örnek çeviri; tam metin Türkçedir.", "Azərbaycanca hələlik yalnız nümunə tərcümədir; tam mətn türkcədir.", "آذربایجانجا هله‌لیک یالنیز اؤرنک ترجمه‌دیر؛ تام متن تورکجه‌دیر."],
        ["source"] = ["منبع", "Kaynak", "Mənbə", "منبع"],
        ["yourShelf"] = ["کتابخانه شما", "Kitaplığınız", "Kitab rəfiniz", "کیتاب رفی‌نیز"],
        ["shelfDescription"] = ["EPUBهای آپلودشده و داستان‌های واردشده", "Yüklediğiniz EPUB ve eklenen öyküler", "Yüklədiyiniz EPUB və əlavə olunan hekayələr", "یوکله‌دیگینیز EPUB و آرتیریلان حکایه‌لر"],
        ["searchShelf"] = ["جست‌وجو در کتابخانه...", "Kütüphanede ara...", "Kitabxanada axtar...", "کیتابخانادا آختار..."],
        ["booksUnit"] = ["کتاب", "kitap", "kitab", "کیتاب"],
        ["shelfEmpty"] = ["هنوز کتابی در کتابخانه نیست.", "Henüz kitap yok.", "Hələ kitab yoxdur.", "هله کیتاب یوخدور."],
        ["shelfEmptySub"] = ["از آثار منتخب شروع کنید یا EPUB اضافه کنید.", "Seçkiden başlayın veya EPUB ekleyin.", "Seçmələrdən başlayın və ya EPUB yükləyin.", "سئچمه‌لردن باشلایین یا EPUB یوکله‌یین."],
        ["continue"] = ["ادامه مطالعه", "Okumaya devam et", "Oxumağa davam et", "اوخوماغا دوام ائت"],
        ["back"] = ["بازگشت به کتابخانه", "Kütüphaneye dön", "Kitabxanaya qayıt", "کیتابخانایا قاییت"],
        ["author"] = ["نویسنده", "Yazar", "Müəllif", "یازار"],
        ["originalLanguage"] = ["زبان اصلی: ترکی استانبولی", "Özgün dil: Türkçe", "Orijinal dil: Türkiyə türkcəsi", "اصلی دیل: تورکیه تورکجه‌سی"],
        ["publicDomain"] = ["اثر کلاسیک · مالکیت عمومی", "Klasik eser · Kamu malı", "Klassik əsər · İctimai mülkiyyət", "کلاسیک اثر · عمومی ملکیت"],
        ["noAuth"] = ["بدون ثبت‌نام", "Kayıt gerekmez", "Qeydiyyatsız", "قئیدیاتسیز"],
        ["readingLanguage"] = ["زبان متن", "Metin dili", "Mətnin dili", "متنین دیلی"],
        ["originalFull"] = ["Türkçe · متن کامل", "Türkçe · Tam metin", "Türkçe · Tam mətn", "Türkçe · تام متن"],
        ["latinSample"] = ["Azərbaycan · نمونه لاتین", "Azerbaycanca · Latin örneği", "Azərbaycanca · Latın nümunəsi", "آذربایجانجا · لاتین اؤرنک"],
        ["arabicSample"] = ["آذربایجانی · نمونه خط عربی", "Azerbaycanca · Arap yazısı örneği", "Azərbaycanca · Ərəb yazısı nümunəsi", "آذربایجانجا · عرب یازیسی اؤرنک"],
        ["sampleWarning"] = ["این بخش فقط نمونه ترجمه است؛ ترجمه کامل هنوز منتشر نشده است.", "Bu yalnızca örnek çeviridir; tam çeviri henüz yok.", "Bu yalnız nümunə tərcümədir; tam tərcümə hələ yoxdur.", "بو یالنیز اؤرنک ترجمه‌دیر؛ تام ترجمه هله یوخدور."],
        ["readFull"] = ["مطالعه متن کامل ترکی", "Tam Türkçe metni oku", "Tam türkcə mətni oxu", "تام تورکجه متنی اوخو"],
        ["preparing"] = ["در حال آماده‌سازی کتاب...", "Kitap hazırlanıyor...", "Kitab hazırlanır...", "کیتاب حاضیرلانیر..."],
        ["openSource"] = ["مشاهده منبع اصلی", "Özgün kaynağı aç", "Orijinal mənbəni aç", "اصلی منبعی آچ"],
        ["downloadError"] = ["دریافت کتاب ممکن نشد؛ منبع اصلی را باز کنید.", "Kitap alınamadı; kaynağı açın.", "Kitabı almaq olmadı; mənbəni açın.", "کیتابی آلماق اولمادی؛ منبعی آچین."],
        ["uploadTitle"] = ["بارگذاری کتاب EPUB", "EPUB kitabı yükle", "EPUB kitabı yüklə", "EPUB کیتابی یوکله"],
        ["uploadHelp"] = ["کتاب‌های خود را به کتابخانه اضافه کنید.", "Kitaplarınızı kütüphaneye ekleyin.", "Kitablarınızı kitabxanaya əlavə edin.", "کیتابلارینیزی کیتابخانایا آرتیرین."],
        ["file"] = ["فایل EPUB", "EPUB dosyası", "EPUB faylı", "EPUB فایلی"],
        ["titleOptional"] = ["عنوان (اختیاری)", "Başlık (isteğe bağlı)", "Başlıq (istəyə bağlı)", "آد (اختیاری)"],
        ["authorOptional"] = ["نویسنده (اختیاری)", "Yazar (isteğe bağlı)", "Müəllif (istəyə bağlı)", "یازار (اختیاری)"],
        ["languageOfBook"] = ["زبان کتاب", "Kitabın dili", "Kitabın dili", "کیتابین دیلی"],
        ["uploading"] = ["در حال آپلود...", "Yükleniyor...", "Yüklənir...", "یوکلنیر..."],
        ["uploadSubmit"] = ["افزودن به کتابخانه", "Kütüphaneye ekle", "Kitabxanaya əlavə et", "کیتابخانایا آرتیر"],
        ["uploadFailed"] = ["آپلود ناموفق بود", "Yükleme başarısız", "Yükləmə uğursuz oldu", "یوکله‌مه باشاریسیز اولدو"],
        ["firstSelect"] = ["ابتدا فایل EPUB را انتخاب کنید.", "Önce EPUB seçin.", "Əvvəl EPUB seçin.", "اول EPUB سئچین."],
        ["reader"] = ["کتاب‌خوان", "Okuyucu", "Oxuyucu", "اوخویوجو"],
        ["previousPage"] = ["صفحه قبل", "Önceki sayfa", "Əvvəlki səhifə", "اؤنجه‌کی صفحه"],
        ["nextPage"] = ["صفحه بعد", "Sonraki sayfa", "Sonrakı səhifə", "سونراکی صفحه"],
        ["page"] = ["صفحه", "Sayfa", "Səhifə", "صفحه"],
        ["of"] = ["از", "/", "/", "/"],
        ["increaseFont"] = ["قلم بزرگ‌تر", "Yazıyı büyüt", "Şrifti böyüt", "یازینی بؤیوت"],
        ["decreaseFont"] = ["قلم کوچک‌تر", "Yazıyı küçült", "Şrifti kiçilt", "یازینی کیچیلت"],
        ["readerLoading"] = ["در حال بازکردن کتاب...", "Kitap açılıyor...", "Kitab açılır...", "کیتاب آچیلیر..."],
        ["readerError"] = ["خواندن فایل EPUB ممکن نشد.", "EPUB okunamadı.", "EPUB oxunmadı.", "EPUB اوخونمادی."],
        ["progressLocal"] = ["آخرین صفحه در مرورگر شما ذخیره می‌شود.", "Son sayfa tarayıcınızda saklanır.", "Son səhifə brauzerinizdə saxlanılır.", "سون صفحه براوزرده ساخ‌لانیر."],
        ["reload"] = ["تلاش مجدد", "Tekrar dene", "Yenidən yoxla", "یئنی‌دن یوخلا"],
        ["readerTip"] = ["با دکمه‌ها یا کلیدهای جهت‌نما ورق بزنید.", "Düğmelerle veya ok tuşlarıyla sayfa çevirin.", "Düymə və ya ox klavişləri ilə səhifə çevirin.", "دویمه‌لر یا اوخ کلیدلری ایله صفحه چئویرین."],
        ["fileMissing"] = ["فایل کتاب یافت نشد.", "Kitap dosyası bulunamadı.", "Kitab faylı tapılmadı.", "کیتاب فایلی تاپیلمادی."],
        ["summary_kasagi"] = ["داستان دو برادر و پیامد یک دروغ.", "İki kardeşin ve bir yalanın sonuçlarının hikâyesi.", "İki qardaş və yalanın nəticələri haqqında hekayə.", "ایکی قارداش و یالانین سونوجلاری حاقیندا حکایه."],
        ["summary_falaka"] = ["روایتی از مدرسه قدیمی و شیوه‌های سخت تربیت.", "Eski bir okul ve sert eğitim yöntemleri.", "Köhnə məktəb və sərt təhsil üsulları.", "کؤهنه مکتب و سرت تحصیل اوسوللاری."],
        ["summary_pembe-incili-kaftan"] = ["روایت عزت‌نفس و شجاعت یک سفیر.", "Bir elçinin onur ve cesaret öyküsü.", "Bir elçinin şərəfi və cəsarəti haqqında hekayə.", "بیر ائلچینین شرف و جسارتی حاقیندا حکایه."],
        ["summary_diyet"] = ["آهنگری آزاده و بهای استقلال او.", "Bağımsız bir demircinin öyküsü.", "Azad bir dəmirçinin hekayəsi.", "آزاد بیر دمیرچینین حکایه‌سی."],
        ["summary_yalniz-efe"] = ["افسانه زن شجاعی در کوهستان.", "Dağlarda cesur bir kadının öyküsü.", "Dağlarda cəsur bir qadının hekayəsi.", "داغلاردا جسور بیر قادینین حکایه‌سی."],
        ["booksCategory"] = ["داستان کوتاه · ترکی", "Kısa öykü · Türkçe", "Qısa hekayə · Türkcə", "قیسا حکایه · تورکجه"],
        ["languagePreview"] = ["پیش‌نمایش زبان", "Dil önizlemesi", "Dil önbaxışı", "دیل اؤن باخیش"],
        ["previewNote"] = ["ترجمه‌های آذربایجانی فقط بخش کوتاهی از اثرند؛ متن کامل به ترکی موجود است.", "Azerbaycan çevirileri yalnızca kısa örnektir; tam metin Türkçedir.", "Azərbaycan tərcümələri qısa nümunədir; tam mətn türkcədir.", "آذربایجان ترجمه‌لری قیسا اؤرنک‌دیر؛ تام متن تورکجه‌دیر."]
    };

    private static int Index(string lang) => lang switch
    {
        "tr" => 1, "az-Latn" => 2, "az-Arab" => 3, _ => 0
    };
    public string T(string key) => Messages.TryGetValue(key, out var words) ? words[Index(Language)] : key;
    public void Set(string? language)
    {
        language = language is "fa" or "tr" or "az-Latn" or "az-Arab" ? language : DefaultLanguage;
        if (Language == language) return;
        Language = language;
        Changed?.Invoke();
    }
}