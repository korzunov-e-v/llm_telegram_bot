from dataclasses import dataclass
from math import ceil

from pydantic import BaseModel
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


class PageItem(BaseModel):
    """
    Элемент инлайн клавиатуры.

    :var cb_data: Строка `callback data`
    :var display_name: Текст на кнопке
    """
    cb_data: str
    display_name: str


@dataclass
class ListPage:
    """
    :var items: общий список из `PageItem`
    :var page: запрошенная страница
    :var per_page: количество элементов на странице
    """
    items: list[PageItem]
    page: int
    per_page: int

    @property
    def total_pages(self) -> int:
        """
        :return: Число страниц пагинации.
        """
        return max(1, ceil(len(self.items) / self.per_page))

    def slice(self):
        """
        Выбрать элементы страницы.
        :return: Список элементов для заданной страницы.
        """
        s = self.page * self.per_page
        return list(self.items[s:s + self.per_page])


def build_list_keyboard(
    items: list[PageItem],
    page: int = 0,
    per_page: int = 8,
    item_cb_prefix: str = "item",
    page_cb_prefix: str = "page",
    back_button_cb: str = None
) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с пагинацией.

    :param items: список src.tools.pagination.PageItem
    :param page: запрошенная страница
    :param per_page: кол-во элементов на странице
    :param item_cb_prefix: префикс callback строки для элемента = `f"{item_cb_prefix}+{item.cb_data}"`
    :param page_cb_prefix: префикс callback строки для пагинатора = `f"{page_cb_prefix}+{page + 1}"`
    :param back_button_cb: опционально: строка callback для кнопки Назад
    :return: клавиатура InlineKeyboardMarkup
    """
    lp = ListPage(items, page, per_page)

    rows = [[InlineKeyboardButton(text=item.display_name, callback_data=f"{item_cb_prefix}+{item.cb_data}")]
            for item in lp.slice()]

    nav = []
    if lp.page > 0:
        nav.append(InlineKeyboardButton("◀︎", callback_data=f"{page_cb_prefix}+{lp.page - 1}"))
    nav.append(InlineKeyboardButton(f"{lp.page + 1}/{lp.total_pages}", callback_data="noop"))
    if lp.page + 1 < lp.total_pages:
        nav.append(InlineKeyboardButton("▶︎", callback_data=f"{page_cb_prefix}+{lp.page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("Отмена", callback_data="cancel+0")])
    if back_button_cb:
        rows.append([InlineKeyboardButton("Назад", callback_data=back_button_cb)])
    return InlineKeyboardMarkup(rows)
