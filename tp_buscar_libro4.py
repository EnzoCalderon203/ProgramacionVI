import flet as ft

def main(page: ft.Page):
    page.title = "Lector de libros - Prototipo"
    page.padding = 20
    page.bgcolor = ft.Colors.WHITE
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # -----------------------
    # Componentes base
    # -----------------------

    def build_search_bar():
        return ft.Container(
            bgcolor="#E0E0E0",
            border_radius=25,
            padding=10,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.SEARCH),
                    ft.Text("Buscar Libro"),
                    ft.Icon(ft.Icons.MENU),
                ],
            ),
        )

    # Tarjeta simple de libro
    def book_card(title):
        return ft.Container(
            border=ft.border.all(1, ft.Colors.BLACK),
            border_radius=20,
            width=100,
            height=150,
            padding=10,
            content=ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Image(src="assets/placeholder_book.png", width=80, height=100, fit=ft.ImageFit.COVER),
                    ft.Text(title, size=12),
                ],
            ),
        )

    # -----------------------
    # Contenido dinámico
    # -----------------------
    current_view = ft.Column(expand=True, spacing=20)

    def show_home():
        current_view.controls.clear()
        current_view.controls.extend([
            build_search_bar(),
            ft.Text("Ahora mismo", weight=ft.FontWeight.BOLD),
            ft.Row([book_card("Libro 1"), book_card("Libro 2"), book_card("Libro 3")], spacing=10),
            ft.Text("Fecha 1"),
            ft.Row([book_card("Libro 4")]),
        ])
        page.update()

    def show_favorites():
        current_view.controls.clear()
        current_view.controls.extend([
            build_search_bar(),
            ft.Text("Favoritos", weight=ft.FontWeight.BOLD),
            ft.Text("Todos los favoritos"),
            ft.Text("Leer más tarde"),
        ])
        page.update()

    def show_explore():
        current_view.controls.clear()
        current_view.controls.extend([
            build_search_bar(),
            ft.Text("Explorar", weight=ft.FontWeight.BOLD),
            ft.Text("Dispositivo"),
            ft.Text("Marcadores"),
        ])
        page.update()

    # -----------------------
    # Barra inferior
    # -----------------------
    def on_nav_change(e):
        idx = e.control.selected_index
        if idx == 0:
            show_home()
        elif idx == 1:
            show_favorites()
        elif idx == 2:
            show_explore()

    nav_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.HISTORY, label="Historial"),
            ft.NavigationBarDestination(icon=ft.Icons.FAVORITE_BORDER, label="Favoritos"),
            ft.NavigationBarDestination(icon=ft.Icons.EXPLORE_OUTLINED, label="Explorar"),
        ],
        selected_index=0,
        on_change=on_nav_change,
    )

    # -----------------------
    # Botón “Continuar” fijo
    # -----------------------
    boton_continuar = ft.Container(
        alignment=ft.alignment.center_right,
        padding=ft.padding.only(top=10),
        content=ft.ElevatedButton(
            "Continuar",
            icon=ft.Icons.MENU_BOOK_OUTLINED,
            bgcolor=ft.Colors.BLUE_400,
            color=ft.Colors.WHITE,
        ),
    )

    # -----------------------
    # Layout general
    # -----------------------
    page.add(
        current_view,
        boton_continuar,
        nav_bar,
    )

    show_home()  # vista inicial


if __name__ == "__main__":
    ft.app(target=main)
