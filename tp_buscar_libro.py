import flet as ft

# Versión 1 - Trabajo Práctico (10%)
# App prototipo sin base de datos ni lectura real de EPUB.
# Solo interfaz y navegación básica según el diseño en Canva.

class BookCard(ft.Container):
    def __init__(self, title: str, cover_src: str | None = None, on_click=None):
        super().__init__()

        self.border = ft.border.all(1, ft.colors.BLACK)
        self.border_radius = 20
        self.padding = 10
        self.width = 110
        self.height = 160
        self.on_click = on_click

        # Imagen de portada (puedes cambiar las rutas o usar un placeholder)
        cover = ft.Image(
            src=cover_src if cover_src else "assets/placeholder_book.png",
            fit=ft.ImageFit.COVER,
            width=90,
            height=110,
        )

        self.content = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=5,
            controls=[
                cover,
                ft.Text(title, size=12, no_wrap=True),
            ],
        )


def main(page: ft.Page):
    page.title = "Lector de libros - Prototipo"
    page.padding = 20
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.bgcolor = ft.colors.WHITE

    # Datos falsos de libros para mostrar en el prototipo
    books_now = [
        {"title": "Libro 1", "cover": "assets/libro1.png"},
        {"title": "Libro 2", "cover": "assets/libro2.png"},
        {"title": "Libro 3", "cover": "assets/libro3.png"},
        {"title": "Libro 4", "cover": "assets/libro4.png"},
    ]

    current_view = ft.Column(expand=True, spacing=20)

    def build_search_bar():
        return ft.Container(
            bgcolor="#E0E0E0",
            border_radius=25,
            padding=10,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.icons.SEARCH),
                    ft.Text("Buscar Libro"),
                    ft.Icon(ft.icons.MENU),
                ],
            ),
        )

    def show_home_view():
        current_view.controls.clear()
        current_view.controls.extend(
            [
                build_search_bar(),
                ft.Text("Ahora mismo", size=14, weight=ft.FontWeight.BOLD),
                ft.Row(
                    controls=[
                        BookCard(b["title"], b["cover"]) for b in books_now[:3]
                    ],
                    spacing=10,
                ),
                ft.Text("Fecha 1", size=12),
                ft.Row(
                    controls=[
                        BookCard(books_now[3]["title"], books_now[3]["cover"])
                    ],
                    spacing=10,
                ),
                ft.Container(
                    alignment=ft.alignment.center_right,
                    content=ft.ElevatedButton(
                        "Continuar",
                        icon=ft.icons.MENU_BOOK_OUTLINED,
                    ),
                ),
            ]
        )
        page.update()

    def show_favorites_view():
        current_view.controls.clear()
        current_view.controls.extend(
            [
                build_search_bar(),
                ft.Text("Favoritos", size=16, weight=ft.FontWeight.BOLD),
                ft.Text("Todos los favoritos"),
                ft.Text("Leer más tarde"),
                ft.Container(
                    alignment=ft.alignment.center_right,
                    content=ft.ElevatedButton(
                        "Continuar",
                        icon=ft.icons.MENU_BOOK_OUTLINED,
                    ),
                ),
            ]
        )
        page.update()

    def show_explore_view():
        current_view.controls.clear()
        current_view.controls.extend(
            [
                build_search_bar(),
                ft.Text("Explorar", size=16, weight=ft.FontWeight.BOLD),
                ft.Text("Dispositivo"),
                ft.Text("Marcadores"),
                ft.Container(
                    alignment=ft.alignment.center_right,
                    content=ft.ElevatedButton(
                        "Continuar",
                        icon=ft.icons.MENU_BOOK_OUTLINED,
                    ),
                ),
            ]
        )
        page.update()

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
            ft.NavigationDestination(icon=ft.icons.HISTORY, label="Historial"),
            ft.NavigationDestination(icon=ft.icons.FAVORITE_BORDER, label="Favoritos"),
            ft.NavigationDestination(icon=ft.icons.EXPLORE_OUTLINED, label="Explorar"),
        ],
        selected_index=0,
        on_change=on_nav_change,
    )

    page.add(
        current_view,
        nav_bar,
    )

    # Vista inicial
    show_home_view()


if __name__ == "__main__":
    ft.app(target=main)
