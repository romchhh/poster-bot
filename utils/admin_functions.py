"""Admin helpers: stats, DB export, mailing text/buttons."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from database_functions.admin_db import (
    get_all_links_data,
    get_all_users_data,
    get_statistics_summary,
)


def parse_url_buttons(text: str) -> list[list[tuple[str, str]]]:
    """Mailing-style URL buttons: rows of (label, url) tuples."""
    buttons: list[list[tuple[str, str]]] = []
    if not text:
        return buttons
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if " | " in line:
            row: list[tuple[str, str]] = []
            for part in line.split(" | "):
                parts = part.split(" - ", 1)
                if len(parts) == 2:
                    row.append((parts[0].strip(), parts[1].strip()))
            if row:
                buttons.append(row)
        else:
            parts = line.split(" - ", 1)
            if len(parts) == 2:
                buttons.append([(parts[0].strip(), parts[1].strip())])
    return buttons


def generate_database_export():
    users_data, users_columns = get_all_users_data()
    links_data, links_columns = get_all_links_data()

    users_df = pd.DataFrame(users_data, columns=users_columns)
    links_df = pd.DataFrame(links_data, columns=links_columns)

    current_date = datetime.now().strftime("%d.%m.%Y_%H-%M")
    filename = f"database_export_{current_date}.xlsx"

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        users_df.to_excel(writer, sheet_name="Користувачі", index=False)
        links_df.to_excel(writer, sheet_name="Посилання", index=False)

        worksheet_users = writer.sheets["Користувачі"]
        column_widths = {
            "A": 12,
            "B": 15,
            "C": 20,
            "D": 20,
            "E": 20,
            "F": 15,
            "G": 10,
            "H": 20,
            "I": 20,
            "J": 15,
        }
        for col, width in column_widths.items():
            worksheet_users.column_dimensions[col].width = width

        header_fill = PatternFill(
            start_color="4472C4", end_color="4472C4", fill_type="solid"
        )
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_alignment = Alignment(horizontal="center", vertical="center")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        for cell in worksheet_users[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment
            cell.border = thin_border

        for row in worksheet_users.iter_rows(
            min_row=2,
            max_row=worksheet_users.max_row,
            min_col=1,
            max_col=len(users_columns),
        ):
            for cell in row:
                cell.border = thin_border
                cell.alignment = Alignment(vertical="center")

        if not links_df.empty:
            worksheet_links = writer.sheets["Посилання"]
            for col, width in {"A": 12, "B": 30, "C": 50}.items():
                worksheet_links.column_dimensions[col].width = width
            for cell in worksheet_links[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = header_alignment
                cell.border = thin_border
            for row in worksheet_links.iter_rows(
                min_row=2,
                max_row=worksheet_links.max_row,
                min_col=1,
                max_col=len(links_columns),
            ):
                for cell in row:
                    cell.border = thin_border
                    cell.alignment = Alignment(vertical="center")

    return filename, len(users_df), len(links_df)


def format_statistics_message() -> str:
    stats = get_statistics_summary()

    language_emoji = {
        "uk": "🇺🇦",
        "ru": "🇷🇺",
        "en": "🇬🇧",
        "pl": "🇵🇱",
        "de": "🇩🇪",
        "fr": "🇫🇷",
        "es": "🇪🇸",
        "it": "🇮🇹",
    }

    languages_text = ""
    for lang, count in stats["languages"]:
        emoji = language_emoji.get(lang, "🌐")
        percentage = (
            (count / stats["total_users"] * 100) if stats["total_users"] > 0 else 0
        )
        languages_text += (
            f"   {emoji} {lang or 'Невідомо'}: {count} ({percentage:.1f}%)\n"
        )

    top_links_text = ""
    if stats["top_links"]:
        for i, (link_name, clicks) in enumerate(stats["top_links"], 1):
            top_links_text += f"   {i}. {link_name}: {clicks} переходів\n"
    else:
        top_links_text = "   Немає даних\n"

    phone_percentage = (
        (stats["users_with_phone"] / stats["total_users"] * 100)
        if stats["total_users"] > 0
        else 0
    )
    links_percentage = (
        (stats["users_from_links"] / stats["total_users"] * 100)
        if stats["total_users"] > 0
        else 0
    )

    return f"""<b>📊 ДЕТАЛЬНА СТАТИСТИКА БОТА</b>

<b>👥 ЗАГАЛЬНА ІНФОРМАЦІЯ</b>
• Всього користувачів: <b>{stats['total_users']}</b>
• З номером телефону: <b>{stats['users_with_phone']}</b> ({phone_percentage:.1f}%)

<b>📈 НОВІ КОРИСТУВАЧІ</b>
• За сьогодні: <b>{stats['new_today']}</b>
• За тиждень: <b>{stats['new_week']}</b>
• За місяць: <b>{stats['new_month']}</b>

<b>⚡️ АКТИВНІ КОРИСТУВАЧІ</b>
• За сьогодні: <b>{stats['active_today']}</b>
• За тиждень: <b>{stats['active_week']}</b>
• За місяць: <b>{stats['active_month']}</b>

<b>🌍 СТАТИСТИКА ПО МОВАХ</b>
{languages_text}
<b>🔗 СТАТИСТИКА ПО ПОСИЛАННЯХ</b>
• Всього посилань: <b>{stats['total_links']}</b>
• Всього переходів: <b>{stats['total_clicks']}</b>
• Користувачів з посилань: <b>{stats['users_from_links']}</b> ({links_percentage:.1f}%)

<b>🏆 ТОП-5 ПОСИЛАНЬ:</b>
{top_links_text}
<i>📅 Оновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"""
