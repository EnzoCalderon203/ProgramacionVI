import os
import base64
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any

import flet as ft

# ==============================================
#   Lector de Libros - Proyecto Final
#   Python 3.14 + Flet (API moderna)
#
#   Requisitos:
#       pip install flet ebooklib beautifulsoup4
# ==============================================

DB_FILE = "reader.db"
COVERS_DIR = "covers"

# --- EPUB libs (opcionales, pero recomendadas) ---
try:
    from ebooklib import epub
    from bs4 import BeautifulSoup
except Exception:
    epub = None
    BeautifulSoup = None


# ------------------------------
#   Dataclasses
# ------------------------------
@dataclass
class Settings:
    font_size: int = 18
    theme: str = "sepia"          # "light", "sepia", "dark"
    font_key: str = "default"     # "default", "serif", "sans"
    line_height: float = 1.4      # interlineado
    margins: bool = True          # márgenes grandes
    bold: bool = False            # texto en negrita


@dataclass
class Book:
    id: int | None = None
    title: str = ""
    author: str = ""
    file_path: Path | None = None
    cover_path: Path | None = None
    is_favorite: bool = False
    is_read: bool = False
    tags: str = ""                # categorías / etiquetas (separadas por comas)
    current_page: int = 0
    total_pages: int = 0


@dataclass
class ChapterPage:
    """Página lógica de lectura (paginada por capítulo)"""
    chapter_index: int
    chapter_title: str
    page_in_chapter: int
    blocks: List[Dict[str, Any]]  # {"type": "text"|"image", ...}


# Mapeo de claves de fuente -> familia del sistema
FONT_FAMILIES: Dict[str, str | None] = {
    "default": None,                # fuente por defecto del sistema
    "serif": "Times New Roman",
    "sans": "Arial",
}


# ------------------------------
#   SQLite helpers
# ------------------------------
def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = conn.cursor()

    # Tabla de libros
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            file_path TEXT NOT NULL,
            cover_path TEXT,
            is_favorite INTEGER NOT NULL DEFAULT 0,
            is_read INTEGER NOT NULL DEFAULT 0,
            current_page INTEGER NOT NULL DEFAULT 0,
            total_pages INTEGER NOT NULL DEFAULT 0,
            author TEXT DEFAULT '',
            tags TEXT DEFAULT ''
        )
        """
    )

    # Tabla de configuración global
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            font_size INTEGER NOT NULL,
            theme TEXT NOT NULL
        )
        """
    )

    # Tabla para recordar el último libro / página abierta
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS last_read (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            book_id INTEGER,
            page INTEGER
        )
        """
    )

    # Fila única de settings
    cur.execute("SELECT COUNT(*) FROM settings WHERE id = 1")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO settings (id, font_size, theme) VALUES (1, ?, ?)",
            (18, "sepia"),
        )

    # Fila única de last_read
    cur.execute("SELECT COUNT(*) FROM last_read WHERE id = 1")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO last_read (id, book_id, page) VALUES (1, NULL, 0)"
        )

    conn.commit()
    return conn


def load_settings(conn: sqlite3.Connection) -> Settings:
    cur = conn.cursor()
    cur.execute("SELECT font_size, theme FROM settings WHERE id = 1")
    row = cur.fetchone()
    if row:
        # valores básicos desde DB, el resto viene por defecto
        return Settings(font_size=row[0], theme=row[1])
    return Settings()


def save_settings(conn: sqlite3.Connection, settings: Settings):
    cur = conn.cursor()
    cur.execute(
        "UPDATE settings SET font_size = ?, theme = ? WHERE id = 1",
        (settings.font_size, settings.theme),
    )
    conn.commit()


def save_last_read(conn: sqlite3.Connection, book: Book):
    """Guarda el último libro / página abiertos."""
    if book.id is None:
        return
    cur = conn.cursor()
    cur.execute(
        "UPDATE last_read SET book_id = ?, page = ? WHERE id = 1",
        (int(book.id), int(book.current_page)),
    )
    conn.commit()


def load_last_read(conn: sqlite3.Connection) -> tuple[int | None, int]:
    """Devuelve (book_id, page)."""
    cur = conn.cursor()
    cur.execute("SELECT book_id, page FROM last_read WHERE id = 1")
    row = cur.fetchone()
    if not row:
        return None, 0
    return int(row[0]) if row[0] is not None else None, int(row[1])


def load_books(conn: sqlite3.Connection) -> List[Book]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, title, file_path, cover_path, is_favorite, is_read,
               current_page, total_pages, author, tags
        FROM books
        """
    )
    books: List[Book] = []
    for row in cur.fetchall():
        books.append(
            Book(
                id=row[0],
                title=row[1],
                file_path=Path(row[2]),
                cover_path=Path(row[3]) if row[3] else None,
                is_favorite=bool(row[4]),
                is_read=bool(row[5]),
                current_page=row[6],
                total_pages=row[7],
                author=row[8] or "",
                tags=row[9] or "",
            )
        )
    return books


def insert_book(conn: sqlite3.Connection, book: Book) -> Book:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO books (title, file_path, cover_path,
                           is_favorite, is_read, current_page, total_pages,
                           author, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            book.title,
            str(book.file_path) if book.file_path else "",
            str(book.cover_path) if book.cover_path else None,
            1 if book.is_favorite else 0,
            1 if book.is_read else 0,
            book.current_page,
            book.total_pages,
            book.author,
            book.tags,
        ),
    )
    conn.commit()
    book.id = cur.lastrowid
    return book


def update_book_progress(conn: sqlite3.Connection, book: Book):
    """Guarda el progreso del libro en la base de datos.

    Cualquier error se ignora para evitar que reviente el hilo de Flet
    cuando el slider envía muchos eventos seguidos.
    """
    if book.id is None:
        return

    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE books "
            "SET is_read = ?, current_page = ?, total_pages = ? "
            "WHERE id = ?",
            (
                1 if book.is_read else 0,
                int(book.current_page),
                int(book.total_pages),
                int(book.id),
            ),
        )
        conn.commit()
    except Exception:
        # Ignoramos cualquier problema (sqlite.Error, SystemError, etc.)
        pass


def update_book_flags(conn: sqlite3.Connection, book: Book):
    """Actualiza favorito / leído / etiquetas."""
    if book.id is None:
        return

    cur = conn.cursor()
    cur.execute(
        """
        UPDATE books
        SET is_favorite = ?, is_read = ?, tags = ?
        WHERE id = ?
        """,
        (
            1 if book.is_favorite else 0,
            1 if book.is_read else 0,
            book.tags,
            int(book.id),
        ),
    )
    conn.commit()


def delete_book(conn: sqlite3.Connection, book: Book):
    """Elimina un libro de la base y borra la portada del disco."""
    if book.id is None:
        return

    cur = conn.cursor()
    cur.execute("DELETE FROM books WHERE id = ?", (int(book.id),))
    conn.commit()

    # borrar portada si existe
    if book.cover_path and book.cover_path.exists():
        try:
            os.remove(book.cover_path)
        except OSError:
            pass


# ------------------------------
#   EPUB helpers avanzados
#   (capítulos, bloques e imágenes)
# ------------------------------
class EpubBook:
    """Representa un EPUB ya parseado en capítulos y bloques."""

    def __init__(self, path: Path):
        if epub is None or BeautifulSoup is None:
            raise RuntimeError(
                "Las librerías 'ebooklib' y 'beautifulsoup4' son necesarias.\n"
                "Instálalas con: pip install ebooklib beautifulsoup4"
            )
        self.path = path
        self.title = path.stem
        self.author = "Desconocido"
        self.chapters: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        book = epub.read_epub(str(self.path))

        # metadata
        t = book.get_metadata("DC", "title")
        a = book.get_metadata("DC", "creator")
        if t:
            self.title = t[0][0]
        if a:
            self.author = a[0][0]

        # mapa de imágenes
        images: Dict[str, bytes] = {}
        for item in book.get_items():
            if isinstance(item, epub.EpubImage):
                images[item.file_name] = item.get_content()

        # documentos HTML (capítulos)
        for item in book.get_items():
            if not isinstance(item, epub.EpubHtml):
                continue

            soup = BeautifulSoup(item.get_content(), "html.parser")
            if not soup.body:
                continue

            heading = soup.find(["h1", "h2", "h3"])
            chap_title = heading.get_text(strip=True) if heading else self.title

            blocks: List[Dict[str, Any]] = []

            for elem in soup.body.descendants:
                # texto (párrafos / títulos)
                if getattr(elem, "name", None) in ("p", "h1", "h2", "h3", "li"):
                    text = elem.get_text(" ", strip=True)
                    if text:
                        blocks.append({"type": "text", "text": text})

                # imágenes
                if getattr(elem, "name", None) == "img":
                    src = elem.get("src")
                    if not src:
                        continue
                    key = src.split("#")[0]
                    key = key.lstrip("./").replace("../", "")

                    if key not in images:
                        only_name = os.path.basename(key)
                        for k in images.keys():
                            if os.path.basename(k) == only_name:
                                key = k
                                break

                    if key in images:
                        b64 = base64.b64encode(images[key]).decode("utf-8")
                        blocks.append(
                            {
                                "type": "image",
                                "data": b64,
                                "alt": elem.get("alt", ""),
                            }
                        )

            if blocks:
                self.chapters.append(
                    {
                        "title": chap_title,
                        "blocks": blocks,
                    }
                )


def get_epub_metadata(path: Path) -> tuple[str, str]:
    """Lee solo título y autor de un EPUB."""
    if epub is None:
        return path.stem, ""
    try:
        book = epub.read_epub(str(path))
        t = book.get_metadata("DC", "title")
        a = book.get_metadata("DC", "creator")
        title = t[0][0] if t else path.stem
        author = a[0][0] if a else ""
        return title, author
    except Exception:
        return path.stem, ""


def chars_per_page(font_size: int) -> int:
    """Aproximación de caracteres por página según tamaño de fuente."""
    base = 3200
    return max(800, int(base * 18 / max(10, font_size)))


def paginate_book(epub_book: EpubBook, settings: Settings) -> List[ChapterPage]:
    """Crea páginas lógicas a partir de los capítulos del EPUB."""
    limit = chars_per_page(settings.font_size)
    pages: List[ChapterPage] = []

    for chap_index, chap in enumerate(epub_book.chapters):
        blocks = chap["blocks"]
        chap_title = chap["title"]

        current_blocks: List[Dict[str, Any]] = []
        current_chars = 0
        page_in_chapter = 1

        def flush_page():
            nonlocal current_blocks, current_chars, page_in_chapter
            if not current_blocks:
                return
            pages.append(
                ChapterPage(
                    chapter_index=chap_index,
                    chapter_title=chap_title,
                    page_in_chapter=page_in_chapter,
                    blocks=current_blocks,
                )
            )
            page_in_chapter += 1
            current_blocks = []
            current_chars = 0

        for blk in blocks:
            if blk["type"] == "text":
                length = len(blk["text"])
                if current_blocks and current_chars + length > limit:
                    flush_page()
                current_blocks.append(blk)
                current_chars += length
            else:  # imagen
                img_cost = int(limit * 0.35)
                if current_blocks and current_chars + img_cost > limit:
                    flush_page()
                current_blocks.append(blk)
                current_chars += img_cost

        flush_page()

    return pages


def extract_cover_image(file_path: Path) -> Path | None:
    """Extrae la portada del EPUB y la guarda en covers/<nombre>.ext"""
    if epub is None:
        return None

    if not os.path.exists(COVERS_DIR):
        os.makedirs(COVERS_DIR, exist_ok=True)

    try:
        book = epub.read_epub(str(file_path))
    except Exception:
        return None

    cover_item = None

    for item in book.get_items():
        media_type = getattr(item, "media_type", "")
        name = getattr(item, "file_name", "") or ""
        if "cover" in str(name).lower() and media_type.startswith("image"):
            cover_item = item
            break

    if cover_item is None:
        for item in book.get_items():
            media_type = getattr(item, "media_type", "")
            if media_type.startswith("image"):
                cover_item = item
                break

    if cover_item is None:
        return None

    media_type = getattr(cover_item, "media_type", "image/jpeg")
    ext = ".png" if "png" in media_type else ".jpg"
    out_path = Path(COVERS_DIR) / (file_path.stem + ext)

    try:
        content = cover_item.get_content()
        with open(out_path, "wb") as f:
            f.write(content)
        return out_path
    except Exception:
        return None


# ------------------------------
#   UI helpers
# ------------------------------
def get_theme_colors(settings: Settings):
    if settings.theme == "light":
        return ft.Colors.WHITE, ft.Colors.BLACK
    if settings.theme == "dark":
        return ft.Colors.BLACK, ft.Colors.WHITE
    # sepia (default)
    return "#F5E3C8", "#5B4636"


class BookCard(ft.Container):
    """Tarjeta visual de libro (se mantiene igual que tu diseño original)."""

    def __init__(self, book: Book):
        super().__init__()

        self.book = book

        if book.total_pages > 0:
            progress = int((book.current_page + 1) / book.total_pages * 100)
        else:
            progress = 0

        cover_src = (
            str(book.cover_path)
            if book.cover_path is not None
            else "assets/placeholder_book.png"
        )

        cover_img = ft.Image(
            src=cover_src,
            fit=ft.ImageFit.COVER,
            width=110,
            height=150,
        )

        stack_controls = [cover_img]
        if progress > 0:
            badge = ft.Container(
                bgcolor=ft.Colors.BLUE_500,
                border_radius=20,
                padding=5,
                content=ft.Text(f"{progress}%", size=10, color=ft.Colors.WHITE),
            )
            badge_container = ft.Container(
                alignment=ft.alignment.bottom_right,
                padding=5,
                content=badge,
            )
            stack_controls.append(badge_container)

        cover_with_badge = ft.Stack(controls=stack_controls)

        self.content = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=5,
            controls=[
                cover_with_badge,
                ft.Text(
                    book.title,
                    size=12,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
        )
        self.padding = 5
        self.width = 120


# ------------------------------
#   App principal
# ------------------------------
def main(page: ft.Page):
    page.title = "Lector de libros - Proyecto Final"
    page.padding = 20
    page.bgcolor = ft.Colors.WHITE
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.window_maximized = True

    conn = init_db()
    settings = load_settings(conn)
    books: List[Book] = load_books(conn)

    # cache de páginas avanzadas (con imágenes)
    pages_cache: Dict[int, List[ChapterPage]] = {}

    current_view = ft.Column(expand=True, spacing=20)

    current_book: Book | None = None
    current_page_index = 0

    # ---------- Barra de búsqueda ----------
    search_field = ft.TextField(
        hint_text="Buscar Libro por título, autor o etiqueta",
        filled=True,
        bgcolor="#E0E0E0",
        border_radius=25,
        border_color="transparent",
        prefix_icon=ft.Icons.SEARCH,
        expand=True,
    )

    def apply_search_filter(book_list: List[Book]) -> List[Book]:
        text = (search_field.value or "").strip().lower()
        if not text:
            return book_list
        result: List[Book] = []
        for b in book_list:
            if (
                text in b.title.lower()
                or text in (b.author or "").lower()
                or text in (b.tags or "").lower()
            ):
                result.append(b)
        return result

    def build_search_bar():
        return ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                search_field,
                ft.IconButton(ft.Icons.MENU),
            ],
        )

    # ---------- FilePicker ----------
    file_picker = ft.FilePicker()

    def open_file_picker(e):
        file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["epub"],
        )

    def on_file_picked(e: ft.FilePickerResultEvent):
        nonlocal books

        if not e.files:
            return

        picked = e.files[0]
        path = Path(picked.path)

        # Leer título / autor reales si es posible
        title, author = get_epub_metadata(path)

        cover_path = extract_cover_image(path)

        new_book = Book(
            title=title,
            author=author,
            file_path=path,
            cover_path=cover_path,
        )
        new_book = insert_book(conn, new_book)
        books.append(new_book)

        page.snack_bar = ft.SnackBar(ft.Text(f"Libro agregado: {title}"))
        page.snack_bar.open = True

        show_explore_view()
        page.update()

    file_picker.on_result = on_file_picked
    page.overlay.append(file_picker)

    # ---------- READER ----------
    reader_top_bar = ft.Container(visible=False)

    bg_color, text_color = get_theme_colors(settings)

    page_container_inner = ft.Container(
        expand=True,
        bgcolor=bg_color,
        padding=20,
        alignment=ft.alignment.top_left,
    )

    # Contenedor animado para cambiar de página suavemente
    page_switcher = ft.AnimatedSwitcher(
        content=ft.Container(),
        expand=True,
        transition=ft.AnimatedSwitcherTransition.SCALE,
        duration=350,
        reverse_duration=350,
    )

    # El contenido real de la página va dentro del AnimatedSwitcher
    page_container_inner.content = page_switcher

    def toggle_reader_panel(e):
        reader_top_bar.visible = not reader_top_bar.visible
        reader_bottom_bar.visible = reader_top_bar.visible
        page.update()

    reader_page_container = ft.GestureDetector(
        on_tap=toggle_reader_panel,
        expand=True,
        content=page_container_inner,
    )

    progress_label = ft.Text("")
    page_slider = ft.Slider(
        min=0,
        max=0,
        value=0,
        divisions=1,
    )

    reader_bottom_bar = ft.Container(
        visible=False,
        content=ft.Column(
            spacing=5,
            controls=[
                progress_label,
                page_slider,
            ],
        ),
    )

    # ---- construir UI de una página a partir de ChapterPage ----
    def build_page_view(page_data: ChapterPage) -> ft.Column:
        font_family = FONT_FAMILIES.get(settings.font_key)
        controls: List[ft.Control] = []

        # Título de capítulo solo en la primera página del capítulo
        if page_data.page_in_chapter == 1:
            style_title = ft.TextStyle(
                size=int(settings.font_size * 1.4),
                height=settings.line_height,
                color=text_color,
                font_family=font_family,
                weight=ft.FontWeight.BOLD,
            )
            controls.append(
                ft.Text(
                    page_data.chapter_title,
                    text_align=ft.TextAlign.CENTER,
                    style=style_title,
                )
            )
            controls.append(ft.Container(height=15))

        for blk in page_data.blocks:
            if blk["type"] == "text":
                style = ft.TextStyle(
                    size=settings.font_size,
                    height=settings.line_height,
                    color=text_color,
                    font_family=font_family,
                    weight=ft.FontWeight.BOLD if settings.bold else None,
                )
                controls.append(
                    ft.Text(
                        blk["text"],
                        text_align=ft.TextAlign.JUSTIFY,
                        style=style,
                    )
                )
                controls.append(ft.Container(height=10))
            elif blk["type"] == "image":
                controls.append(
                    ft.Container(
                        alignment=ft.alignment.center,
                        padding=10,
                        content=ft.Image(
                            src_base64=blk["data"],
                            fit=ft.ImageFit.CONTAIN,
                        ),
                    )
                )

        if not controls:
            controls.append(
                ft.Text(
                    "(Sin contenido)",
                    style=ft.TextStyle(size=settings.font_size, color=text_color),
                )
            )

        # IMPORTANTE: el contenido de la página tiene scroll con la ruedita
        return ft.Column(
            controls=controls,
            spacing=0,
            expand=True,
            scroll=ft.ScrollMode.ALWAYS,
        )

    # ---------- Aplicar tema / cambios de fuente ----------
    def apply_theme_to_reader():
        nonlocal bg_color, text_color
        bg_color, text_color = get_theme_colors(settings)
        page_container_inner.bgcolor = bg_color
        page_container_inner.padding = 40 if settings.margins else 10
        if current_book is not None:
            show_page()

    # ---------- Paginación / navegación ----------
    def get_pages_for_book(book: Book) -> List[ChapterPage]:
        if book.id is not None and book.id in pages_cache:
            return pages_cache[book.id]

        if not book.file_path or not book.file_path.exists():
            pages = [
                ChapterPage(
                    chapter_index=0,
                    chapter_title=book.title or "(Sin título)",
                    page_in_chapter=1,
                    blocks=[
                        {
                            "type": "text",
                            "text": "No se encuentra el archivo del libro.",
                        }
                    ],
                )
            ]
        else:
            try:
                eb = EpubBook(book.file_path)
                # actualizamos metadatos si todavía no los tenemos
                if not book.title and eb.title:
                    book.title = eb.title
                if not book.author and eb.author:
                    book.author = eb.author
                pages = paginate_book(eb, settings)
            except Exception as exc:
                pages = [
                    ChapterPage(
                        chapter_index=0,
                        chapter_title=book.title or "(Sin título)",
                        page_in_chapter=1,
                        blocks=[
                            {
                                "type": "text",
                                "text": f"Error al leer el EPUB:\n{exc}",
                            }
                        ],
                    )
                ]

        if book.id is not None:
            pages_cache[book.id] = pages
        book.total_pages = len(pages)
        if book.current_page >= book.total_pages:
            book.current_page = 0
        update_book_progress(conn, book)
        return pages

    def show_page():
        nonlocal current_page_index
        if current_book is None:
            return

        pages = get_pages_for_book(current_book)
        if not pages:
            return

        if current_page_index < 0:
            current_page_index = 0
        if current_page_index >= len(pages):
            current_page_index = len(pages) - 1

        current_book.current_page = current_page_index
        current_book.is_read = True
        current_book.total_pages = len(pages)
        update_book_progress(conn, current_book)
        save_last_read(conn, current_book)

        page_data = pages[current_page_index]
        body = build_page_view(page_data)
        page_switcher.content = body

        global_page = current_page_index + 1
        total = len(pages)
        chap_page = page_data.page_in_chapter
        progress_label.value = (
            f"Capítulo {page_data.chapter_index + 1} · "
            f"Página {chap_page} · Global {global_page}/{total}"
        )

        page_slider.min = 0
        page_slider.max = len(pages) - 1
        page_slider.divisions = max(len(pages) - 1, 1)
        page_slider.value = current_page_index

        page.update()

    def on_slider_change(e):
        nonlocal current_page_index
        current_page_index = int(e.control.value)
        show_page()

    page_slider.on_change = on_slider_change

    # ---------- Navegación con teclado (flechas) ----------
    def handle_keyboard(e: ft.KeyboardEvent):
        nonlocal current_page_index

        # Solo navegar si hay un libro abierto
        if current_book is None:
            return

        # Flecha derecha: página siguiente
        if e.key in ("ArrowRight", "Arrow Right"):
            pages = get_pages_for_book(current_book)
            if current_page_index < len(pages) - 1:
                current_page_index += 1
                show_page()

        # Flecha izquierda: página anterior
        elif e.key in ("ArrowLeft", "Arrow Left"):
            if current_page_index > 0:
                current_page_index -= 1
                show_page()

    # Registramos el manejador de teclado en la página
    page.on_keyboard_event = handle_keyboard

    # ---------- Configuración (BottomSheet) ----------
    font_slider = ft.Slider(
        min=12,
        max=30,
        divisions=18,
        value=settings.font_size,
        label="{value}",
    )

    theme_dropdown = ft.Dropdown(
        options=[
            ft.dropdown.Option("light"),
            ft.dropdown.Option("sepia"),
            ft.dropdown.Option("dark"),
        ],
        value=settings.theme,
    )

    font_dropdown = ft.Dropdown(
        options=[
            ft.dropdown.Option(key="default", text="Sistema (por defecto)"),
            ft.dropdown.Option(key="serif", text="Serif (Times New Roman)"),
            ft.dropdown.Option(key="sans", text="Sans (Arial)"),
        ],
        value=settings.font_key,
    )

    line_height_slider = ft.Slider(
        min=1.2,
        max=2.0,
        divisions=8,
        value=settings.line_height,
        label="{value}",
    )

    margins_switch = ft.Switch(
        label="Márgenes de la página", value=settings.margins
    )

    bold_switch = ft.Switch(
        label="Fuente en negrita", value=settings.bold
    )

    def save_settings_click(e):
        settings.font_size = int(font_slider.value)
        settings.theme = theme_dropdown.value or "sepia"
        settings.font_key = font_dropdown.value or "default"
        settings.line_height = float(line_height_slider.value)
        settings.margins = margins_switch.value
        settings.bold = bold_switch.value

        save_settings(conn, settings)
        apply_theme_to_reader()
        page.close(settings_sheet)

    def close_settings_click(e):
        page.close(settings_sheet)

    settings_sheet = ft.BottomSheet(
        content=ft.Container(
            padding=20,
            content=ft.Column(
                tight=True,
                spacing=10,
                controls=[
                    ft.Text("Configuración de lectura", weight=ft.FontWeight.BOLD),
                    ft.Text("Modo de color"),
                    theme_dropdown,
                    ft.Text("Tipo de fuente"),
                    font_dropdown,
                    ft.Text("Tamaño de la fuente"),
                    font_slider,
                    ft.Text("Interlineado"),
                    line_height_slider,
                    margins_switch,
                    bold_switch,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.TextButton("Cancelar", on_click=close_settings_click),
                            ft.ElevatedButton("Guardar", on_click=save_settings_click),
                        ],
                    ),
                ],
            ),
        )
    )

    def open_settings_dialog(e):
        page.open(settings_sheet)

    # ---------- Menú contextual de libro (favoritos / etiquetas / borrar) ----------
    def refresh_current_view():
        idx = nav_bar.selected_index
        if idx == 0:
            show_home_view()
        elif idx == 1:
            show_favorites_view()
        else:
            show_explore_view()

    def open_book_menu(book: Book):
        def close_bs(e=None):
            page.close(bs)

        def toggle_favorite(e):
            book.is_favorite = not book.is_favorite
            update_book_flags(conn, book)
            page.snack_bar = ft.SnackBar(
                ft.Text(
                    "Añadido a favoritos"
                    if book.is_favorite
                    else "Eliminado de favoritos"
                )
            )
            page.snack_bar.open = True
            refresh_current_view()
            page.update()
            close_bs(e)

        def toggle_read(e):
            # si estaba leído, lo marcamos como no leído y reiniciamos progreso
            if book.is_read:
                book.is_read = False
                book.current_page = 0
                book.total_pages = book.total_pages  # se mantiene
            else:
                book.is_read = True
            update_book_progress(conn, book)
            update_book_flags(conn, book)
            refresh_current_view()
            page.update()
            close_bs(e)

        def edit_tags(e):
            close_bs(e)

            tag_field = ft.TextField(
                label="Etiquetas / categorías (separadas por comas)",
                value=book.tags,
                multiline=True,
                min_lines=1,
                max_lines=3,
                width=400,
            )

            def close_dialog(ev=None):
                page.close(dialog)

            def save_tags(ev):
                book.tags = tag_field.value.strip()
                update_book_flags(conn, book)
                refresh_current_view()
                page.update()
                close_dialog(ev)

            dialog = ft.AlertDialog(
                title=ft.Text("Editar etiquetas / categorías"),
                content=tag_field,
                actions=[
                    ft.TextButton("Cancelar", on_click=close_dialog),
                    ft.ElevatedButton("Guardar", on_click=save_tags),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.dialog = dialog
            dialog.open = True
            page.update()

        def confirm_delete(e):
            close_bs(e)

            def close_dialog(ev=None):
                page.close(dialog)

            def do_delete(ev):
                nonlocal current_book, current_page_index
                if current_book is not None and current_book.id == book.id:
                    current_book = None
                    current_page_index = 0
                delete_book(conn, book)
                if book in books:
                    books.remove(book)
                refresh_current_view()
                page.update()
                close_dialog(ev)

            dialog = ft.AlertDialog(
                title=ft.Text("Eliminar libro"),
                content=ft.Text(
                    f"¿Seguro que quieres eliminar '{book.title}' de la biblioteca?"
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=close_dialog),
                    ft.ElevatedButton("Eliminar", on_click=do_delete),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.dialog = dialog
            dialog.open = True
            page.update()

        bs = ft.BottomSheet(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Text(book.title, weight=ft.FontWeight.BOLD, size=14),
                        ft.Text(
                            (book.author or "").strip(),
                            size=11,
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Divider(),
                        ft.TextButton(
                            "Marcar como favorito"
                            if not book.is_favorite
                            else "Quitar de favoritos",
                            on_click=toggle_favorite,
                        ),
                        ft.TextButton(
                            "Marcar como leído"
                            if not book.is_read
                            else "Marcar como no leído",
                            on_click=toggle_read,
                        ),
                        ft.TextButton(
                            "Editar etiquetas / categorías",
                            on_click=edit_tags,
                        ),
                        ft.TextButton(
                            "Eliminar libro",
                            on_click=confirm_delete,
                            style=ft.ButtonStyle(
                                color=ft.Colors.RED_400,
                            ),
                        ),
                    ],
                ),
            )
        )
        page.open(bs)

    # ---------- Vistas ----------
    def open_reader(book: Book):
        nonlocal current_book, current_page_index
        current_book = book
        current_page_index = book.current_page

        # Modo lectura: ventana maximizada y sin padding,
        # pero sin usar window_full_screen para evitar el bug de pantalla negra
        page.window_maximized = True
        page.padding = 0
        page.update()

        reader_top_bar.content = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(
                    ft.Icons.ARROW_BACK,
                    on_click=lambda e: show_home_view(),
                ),
                ft.Column(
                    spacing=0,
                    controls=[
                        ft.Text(book.title, weight=ft.FontWeight.BOLD, size=14),
                        ft.Text("Modo lectura", size=11),
                    ],
                ),
                ft.IconButton(ft.Icons.SETTINGS, on_click=open_settings_dialog),
            ],
        )
        reader_top_bar.visible = False
        reader_bottom_bar.visible = False

        nav_bar.visible = False
        boton_continuar.visible = False

        current_view.spacing = 0
        current_view.controls.clear()
        current_view.controls.extend(
            [
                reader_top_bar,
                reader_page_container,
                reader_bottom_bar,
            ]
        )
        apply_theme_to_reader()
        show_page()

    def build_books_row(book_list: List[Book]):
        if not book_list:
            return ft.Text("No hay libros para mostrar.")
        return ft.Row(
            controls=[
                ft.GestureDetector(
                    content=BookCard(b),
                    on_tap=lambda e, bk=b: open_reader(bk),
                    on_long_press=lambda e, bk=b: open_book_menu(bk),
                )
                for b in book_list
            ],
            spacing=10,
            scroll=ft.ScrollMode.AUTO,
        )

    def show_home_view():
        # Salimos de modo lectura: restaurar padding, mantener ventana maximizda
        page.window_maximized = True
        page.padding = 20

        nav_bar.visible = True
        boton_continuar.visible = True
        reader_top_bar.visible = False
        reader_bottom_bar.visible = False

        current_view.spacing = 20
        current_view.controls.clear()
        current_view.controls.append(build_search_bar())
        current_view.controls.append(
            ft.Text("Historial de lectura", size=14, weight=ft.FontWeight.BOLD)
        )

        read_books = [b for b in books if b.is_read]
        read_books = apply_search_filter(read_books)
        current_view.controls.append(build_books_row(read_books))

        page.update()

    def show_favorites_view():
        page.window_maximized = True
        page.padding = 20

        nav_bar.visible = True
        boton_continuar.visible = True
        reader_top_bar.visible = False
        reader_bottom_bar.visible = False

        current_view.spacing = 20
        current_view.controls.clear()
        current_view.controls.append(build_search_bar())
        current_view.controls.append(
            ft.Text("Favoritos", size=16, weight=ft.FontWeight.BOLD)
        )

        favs = [b for b in books if b.is_favorite]
        favs = apply_search_filter(favs)
        current_view.controls.append(build_books_row(favs))

        page.update()

    def show_explore_view():
        page.window_maximized = True
        page.padding = 20

        nav_bar.visible = True
        boton_continuar.visible = True
        reader_top_bar.visible = False
        reader_bottom_bar.visible = False

        current_view.spacing = 20
        current_view.controls.clear()
        current_view.controls.append(build_search_bar())
        current_view.controls.append(
            ft.Text("Explorar", size=16, weight=ft.FontWeight.BOLD)
        )

        current_view.controls.append(
            ft.ElevatedButton(
                "Agregar EPUB desde el dispositivo",
                icon=ft.Icons.ADD,
                on_click=open_file_picker,
            )
        )

        current_view.controls.append(ft.Text("Biblioteca"))
        current_view.controls.append(build_books_row(apply_search_filter(books)))

        page.update()

    # ---------- Barra de navegación ----------
    def on_nav_change(e: ft.ControlEvent):
        idx = e.control.selected_index
        if idx == 0:
            show_home_view()
        elif idx == 1:
            show_favorites_view()
        elif idx == 2:
            show_explore_view()

    nav_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.HISTORY, label="Historial"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.FAVORITE_BORDER, label="Favoritos"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.EXPLORE_OUTLINED, label="Explorar"
            ),
        ],
        selected_index=0,
        on_change=on_nav_change,
    )

    # Ahora que existe nav_bar podemos activar la búsqueda
    def on_search_change(e):
        refresh_current_view()

    search_field.on_change = on_search_change

    # ---------- Botón "Continuar" mejorado ----------
    def continuar_click(e):
        # 1) Intentar usar el último libro / página abiertos
        last_book_id, last_page = load_last_read(conn)
        target_book: Book | None = None

        if last_book_id is not None:
            for b in books:
                if b.id == last_book_id:
                    target_book = b
                    # nos aseguramos de que la página esté en rango
                    if b.total_pages > 0:
                        last_page = max(0, min(last_page, b.total_pages - 1))
                    else:
                        last_page = max(0, last_page)
                    b.current_page = last_page
                    break

        # 2) Si nunca se abrió nada, usamos la lógica anterior
        if target_book is None:
            if books:
                read_books = [b for b in books if b.is_read]
                target_book = read_books[0] if read_books else books[0]
            else:
                page.snack_bar = ft.SnackBar(
                    ft.Text("No hay libros para continuar.")
                )
                page.snack_bar.open = True
                page.update()
                return

        open_reader(target_book)

    boton_continuar = ft.Container(
        alignment=ft.alignment.center_right,
        padding=ft.padding.only(top=10, bottom=5),
        content=ft.ElevatedButton(
            "Continuar",
            icon=ft.Icons.MENU_BOOK_OUTLINED,
            bgcolor=ft.Colors.BLUE_400,
            color=ft.Colors.WHITE,
            on_click=continuar_click,
        ),
    )

    # ---------- Layout general ----------
    page.add(
        current_view,
        boton_continuar,
        nav_bar,
    )

    show_home_view()


if __name__ == "__main__":
    ft.app(target=main)
