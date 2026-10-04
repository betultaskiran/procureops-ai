"""
app/services/extraction/pdf_parser.py

PDF dosyasından ham metin çıkarır.

NEDEN PDFPLUMBER?
  pdfplumber, tedarikçi teklifleri için en uygun kütüphanedir çünkü:
  - Tablo extraction: Fiyat tabloları olan PDF'ler yaygın
  - Karakter koordinatları: Sütun hizalamasını korur
  - Başlık/footer tespiti: Tekrarlayan içerikleri atlar
  - Açık kaynak, aktif geliştirme

SCANNED PDF:
  pdfplumber sadece text-layer olan PDF'lerle çalışır.
  Taranmış belgeler (resim olarak kaydedilmiş) için OCR gerekir.
  Phase 3'te bu case henüz desteklenmez.
  Eğer extract_text() None döndürürse → ScannedPDFError fırlatırız.

TABLO FORMATLAMA:
  pdfplumber tabloları 2D liste olarak döndürür:
  [["Ürün", "Miktar", "Fiyat"], ["Laptop", "50", "4500"], ...]

  Bunu LLM'e göndermeden önce okunabilir hale getiriyoruz:
  Ürün | Miktar | Fiyat
  Laptop | 50 | 4500
"""

from pathlib import Path


# pdfplumber import'unu try/except ile sarıyoruz.
# Bu sayede kütüphane yüklü değilse net bir hata alırsın.
try:
    import pdfplumber
except ImportError as e:
    raise ImportError(
        "pdfplumber is required for PDF parsing. "
        "Add it to pyproject.toml: 'pdfplumber>=0.11.0'"
    ) from e


class PDFParseError(Exception):
    """PDF açılamadı veya metin çıkarılamadı."""
    pass


class ScannedPDFError(PDFParseError):
    """
    PDF'den metin çıkarılamadı — muhtemelen taranmış (scanned) belge.
    Bu durumda OCR gerekir (Phase 3 extension).
    """
    pass


def _format_table(table: list[list]) -> str:
    """
    2D liste halindeki tablo verisini LLM için okunabilir metne çevirir.

    Input:  [["Ürün", "Adet", "Birim Fiyat"], ["Laptop", "50", "4500.00"]]
    Output: "Ürün | Adet | Birim Fiyat\nLaptop | 50 | 4500.00"
    """
    rows = []
    for row in table:
        # None hücreleri boş string'e çevir, strip et
        cells = [str(cell or "").strip() for cell in row]
        # Boş satırları atla
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def extract_text_from_pdf(file_path: str | Path) -> str:
    """
    PDF dosyasından metin ve tablo içeriğini çıkarır.

    Returns:
        Tüm sayfaların birleştirilmiş metni.
        Format:
          --- Page 1 ---
          [metin içeriği]
          [TABLES]
          [tablo içeriği]

          --- Page 2 ---
          ...

    Raises:
        PDFParseError:    PDF açılamadı (bozuk dosya, şifreli vb.)
        ScannedPDFError:  PDF'de metin katmanı yok (taranmış)
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise PDFParseError(f"File not found: {file_path}")

    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages:
                raise PDFParseError("PDF has no pages")

            page_contents = []
            total_text_length = 0

            for page_num, page in enumerate(pdf.pages, start=1):
                page_parts = [f"--- Page {page_num} ---"]

                # ── Metin çıkar ────────────────────────────────────────────────
                page_text = page.extract_text(
                    x_tolerance=3,     # Yatay karakter toleransı
                    y_tolerance=3,     # Dikey karakter toleransı
                    layout=True,       # Sütun hizalamasını koru
                ) or ""

                if page_text.strip():
                    page_parts.append(page_text.strip())
                    total_text_length += len(page_text)

                # ── Tablo çıkar ────────────────────────────────────────────────
                # explicit_vertical_lines / horizontal_lines parametreleri
                # tablo tespitini iyileştirir.
                tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "snap_tolerance": 3,
                    "join_tolerance": 3,
                })

                if tables:
                    table_texts = []
                    for table in tables:
                        if table:
                            formatted = _format_table(table)
                            if formatted.strip():
                                table_texts.append(formatted)

                    if table_texts:
                        page_parts.append("\n[TABLES]\n" + "\n\n".join(table_texts))

                page_contents.append("\n".join(page_parts))

            if total_text_length == 0:
                raise ScannedPDFError(
                    "No text could be extracted from this PDF. "
                    "The document may be scanned (image-based). "
                    "OCR support will be added in a future phase."
                )

            return "\n\n".join(page_contents)

    except (PDFParseError, ScannedPDFError):
        raise
    except Exception as e:
        raise PDFParseError(f"Failed to parse PDF: {e}") from e


def get_page_count(file_path: str | Path) -> int:
    """PDF'deki sayfa sayısını döndürür. Validation için kullanılır."""
    try:
        with pdfplumber.open(file_path) as pdf:
            return len(pdf.pages)
    except Exception as e:
        raise PDFParseError(f"Cannot read PDF: {e}") from e
