# -*- coding: utf-8 -*-
import re
import aqt
import aqt.main
import anki
import anki.collection
from aqt.qt import *
from aqt import gui_hooks
from aqt.operations import QueryOp
from aqt.import_export.exporting import Exporter, ExportOptions, export_progress_update
from aqt.utils import tooltip, tr
from anki.utils import split_fields
from anki.collection import (
    ExportLimit,
    DeckIdLimit,
    NoteIdsLimit,
)


class LatexNoteExporter(Exporter):
    extension = "tex"
    show_deck_list = True
    show_include_tags = True
    show_include_guid = True

    @staticmethod
    def name() -> str:
        return "Notes in Latex"

    def export(self, mw: aqt.main.AnkiQt, options: ExportOptions) -> None:
        options = gui_hooks.exporter_will_export(options, self)

        def on_success(count: int) -> None:
            gui_hooks.exporter_did_export(options, self)
            tooltip(tr.exporting_card_exported(count=self.count), parent=mw)

        QueryOp(
            parent=mw,
            op=lambda col: self.export_note_latex(
                mw=mw,
                col=col,
                out_path=options.out_path,
                options=options,
            ),
            success=on_success,
        ).with_backend_progress(export_progress_update).run_in_background()

    def export_note_latex(
        self,
        mw: aqt.main.AnkiQt,
        col: anki.collection.Collection,
        out_path: str,
        options: ExportOptions,
    ) -> None:
        notes = []
        TAB = "    "

        for guid, note_id, flds, tags, notetype_id in col.db.execute(
            self.db_query(options.limit)
        ):
            note_lines = []
            model = col.models.get(notetype_id)

            note_lines.append(r"\begin{note}")
            # Currently only exports note_id as unique identifier instead of guid as it 
            # contains special characters which lead to problems in latex even when escaped
            if options.include_guid:
                note_lines.append("\\xplain{" + self.escape_latex_chars(str(note_id)) + "}")

            for field in split_fields(flds):
                field = self.replace_line_breaks(field)

                if field.find("[latex]") != -1:
                    # Treat as latex field
                    field = self.convert_html_to_latex(field)
                    # Export field as xfield if it consists of a single line
                    if field.find("\n") == -1:
                        note_lines.append(TAB + r"\xfield{" + field + "}")
                    else:
                        field = self.strip_new_lines(field)
                        field = TAB + TAB + field.replace("\n", "\n" + TAB + TAB)
                        note_lines.append(
                            TAB
                            + r"\begin{field}"
                            + "\n"
                            + field
                            + "\n"
                            + TAB
                            + r"\end{field}"
                        )
                else:
                    # Treat as plain-text field
                    # Export field as xplain field if it consists of a single line
                    if field.find("\n") == -1:
                        note_lines.append(TAB + r"\xplain{" + field + "}")
                    else:
                        field = self.convert_html_to_latex(field)
                        field = self.strip_new_lines(field)
                        field = TAB + TAB + field.replace("\n", "\n" + TAB + TAB)
                        note_lines.append(
                            TAB
                            + r"\begin{plain}"
                            + "\n"
                            + field
                            + "\n"
                            + TAB
                            + r"\end{plain}"
                        )
            # Remove empty fields at the end of the note:
            while note_lines[-1] == TAB + r"\xplain{}":
                note_lines.pop()
            # Tags
            if options.include_tags:
                cleantag = tags.strip()
                if cleantag != "":
                    note_lines.append(TAB + r"\tags{" + tags.strip() + r"}")

            note_lines.append(r"\end{note}" + "\n")
            notes.append("\n".join(note_lines))
        self.count = len(notes)
        out = (
            "% -*- coding: utf-8 -*-\n"
            + model["latexPre"]
            + "\n"
            + "\n".join(notes)
            + "\n"
            + model["latexPost"]
        )
        with open(out_path, mode="w", encoding="utf-8") as file:
            file.write(out)

    def db_query(self, limit: ExportLimit) -> str:
        """Request the notes to be exported from the database by
        deck id or noteid
        """

        if type(limit) == DeckIdLimit:
            query = (
                "SELECT n.guid, n.id, n.flds, n.tags, n.mid "
                "FROM notes n JOIN cards c ON n.id = c.nid "
                "WHERE c.did IN "
                "(SELECT id FROM decks "
                "WHERE name LIKE ("
                f"SELECT name FROM decks WHERE id={limit.deck_id}) || '%')"
            )
        elif type(limit) == NoteIdsLimit:
            query = (
                "SELECT n.guid, n.id, n.flds, n.tags, n.mid "
                "FROM notes n JOIN cards c ON n.id = c.nid "
                f"WHERE n.id IN {tuple(limit.note_ids)}"
            )
        else:
            raise Exception(f"ExportLimit does neither have type DeckIdLimit nor NoteIdsLimit")
        return query

    def replace_line_breaks(self, text: str) -> str:
        """Replace html-line breaks by plain-text line breaks"""
        # Remove plain-text line breaks
        text = text.replace("\n", "")
        # Convert some html
        htmldict = {
            r"<br>": "\n",
            r"<br />": "\n",
            r"<div>": "\n",
            r"</div>": "",
            r"&nbsp;": r" ",
        }
        for k, v in htmldict.items():
            text = text.replace(k, v)
        return text

    def strip_new_lines(self, text: str) -> str:
        """Remove newlines at beginning and end of text and
        replace double blank lines by single blank lines
        """
        text = re.sub("\n\s*\n+", "\n\n", text).strip()
        return text

    def escape_latex_chars(self, text: str) -> str:
        """Escapes all special and command chars in string"""
        text = re.sub(r"([#$%^&_}{~])", r"\\\1", text)
        return text

    def convert_html_to_latex(self, text: str) -> str:
        """Replaces certain html characters and converts html tags
        to their latex equivalents
        """
        # Replace html specifc characters
        htmldict = {r"&amp;": r"&", r"&lt;": r"<", r"&gt;": r">"}
        for k, v in htmldict.items():
            text = text.replace(k, v)
        # Remove latex marks and any surrounding line breaks
        text = re.sub("\n*\[latex\]", "", text)
        text = re.sub("\[/latex\]\n*", "", text)
        # Replace <ul>
        text = re.sub(r"<ul.*?>", r"\\begin{itemize}\n", text)
        text = re.sub(r"</ul>", r"\\end{itemize}", text)
        # Replace <ol>
        text = re.sub(r"<ol.*?>", r"\\begin{enumerate}\n", text)
        text = re.sub(r"</ol>", r"\\end{enumerate}", text)
        # Replace <li>
        text = re.sub(r"<li.*?>", r"\\item ", text)
        text = re.sub(r"</li>", r"\n", text)
        # Replace bold text to latex bold
        text = re.sub(r"<b>(.*?)</b>", r"\\textbf{\1}", text)
        # Convert italic to latex italic
        text = re.sub(r"<i>(.*?)</i>", r"\\textit{\1}", text)
        # Replace <i> underline
        text = re.sub(r"<u>(.*?)</u>", r"\\underline{\1}", text)
        # Replace <sub> subscript
        text = re.sub(r"<sub>(.*?)</sub>", r"\\textsubscript{\1}", text)
        # Replace <sup> superscript
        text = re.sub(r"<sup>(.*?)</sup>", r"\\textsuperscript{\1}", text)
        # Fix Double Newline
        text = re.sub(r"\n\s*\n+", "\n", text)
        # Remove any remaining html tags
        text = re.sub("<[^<]+?>", "", text)
        return text


def addExporterToList(exporters_list) -> None:
    exporters_list.append(LatexNoteExporter)


gui_hooks.exporters_list_did_initialize.append(addExporterToList)
