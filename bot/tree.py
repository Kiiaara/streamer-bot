"""Универсальное дерево контента для навигации.

Строится из плоского списка ContentItem с уровнями section -> category -> subcategory.
Любой уровень можно пропустить (оставив поле пустым в Sheets).

Узел дерева хранит детей и (если он листовой) сам ContentItem.
Callback-data использует числовые индексы (n:0:1:2) - чтобы не упираться в лимит 64 байта.
"""
from dataclasses import dataclass, field
from typing import Optional

from .sheets import ContentItem, SheetsData


@dataclass
class Node:
    label: str
    children: list["Node"] = field(default_factory=list)
    item: Optional[ContentItem] = None  # листовой узел - конкретная ссылка

    def is_leaf(self) -> bool:
        return self.item is not None


def build_tree(data: SheetsData, filter_section: str | None = None) -> Node:
    """Строит дерево разделов из плоского списка контента.
    filter_section - если задан, в дереве будет только этот раздел (для тематических чатов)."""
    root = Node(label="Главное меню")

    items = data.content
    if filter_section:
        items = [i for i in items if i.section == filter_section]
    else:
        # В обычном режиме (главное меню) скрытые разделы не показываем
        hidden_names = {name for name, info in data.sections.items() if info.hidden}
        if hidden_names:
            items = [i for i in items if i.section not in hidden_names]

    # Порядок разделов берём из таблицы sections (Section.position), а не из порядка записей
    section_order = {info.name: info.position for info in data.sections.values()}
    items = sorted(items, key=lambda i: (section_order.get(i.section.strip(), 9999), i.section))

    # Группируем по section -> category -> subcategory с сохранением порядка из таблицы
    sections: dict[str, Node] = {}
    cats: dict[tuple[str, str], Node] = {}
    subcats: dict[tuple[str, str, str], Node] = {}

    for item in items:
        sec = item.section.strip()
        cat = item.category.strip()
        sub = item.subcategory.strip()
        if not sec:
            continue

        if sec not in sections:
            sections[sec] = Node(label=sec)
            root.children.append(sections[sec])
        sec_node = sections[sec]

        if not cat and not sub:
            sec_node.children.append(Node(label=item.title, item=item))
            continue

        if cat:
            key_c = (sec, cat)
            if key_c not in cats:
                cats[key_c] = Node(label=cat)
                sec_node.children.append(cats[key_c])
            cat_node = cats[key_c]

            if not sub:
                cat_node.children.append(Node(label=item.title, item=item))
                continue

            key_s = (sec, cat, sub)
            if key_s not in subcats:
                subcats[key_s] = Node(label=sub)
                cat_node.children.append(subcats[key_s])
            subcats[key_s].children.append(Node(label=item.title, item=item))
        else:
            # subcategory без category - редкий случай, кладём как ребёнка раздела
            sec_node.children.append(Node(label=item.title, item=item))

    return root


def resolve_path(root: Node, indices: list[int]) -> tuple[Node, list[Node]]:
    """По списку индексов возвращает (целевой узел, путь от корня без корня)."""
    node = root
    path: list[Node] = []
    for i in indices:
        if i < 0 or i >= len(node.children):
            return root, []
        node = node.children[i]
        path.append(node)
    return node, path
