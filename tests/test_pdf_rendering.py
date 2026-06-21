import unittest

try:
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
except Exception:  # pragma: no cover - environment-dependent optional dependency
    colors = None
    getSampleStyleSheet = None
    inch = None
    Paragraph = None
    Spacer = None
    Table = None
    TableStyle = None

from src.post_change_validation_pdf_rendering import append_detail_table, pdf_paragraph


@unittest.skipIf(Paragraph is None, "reportlab is not installed")
class PdfRenderingTests(unittest.TestCase):
    def test_pdf_paragraph_escapes_text_for_reportlab_markup(self):
        styles = getSampleStyleSheet()

        paragraph = pdf_paragraph(Paragraph, "value <unsafe>", styles["Normal"])

        self.assertEqual("value <unsafe>", paragraph.getPlainText())

    def test_append_detail_table_adds_expected_flowables_and_skips_empty_rows(self):
        styles = getSampleStyleSheet()
        story = []

        append_detail_table(
            story,
            "Port Map Detail",
            "Finding <summary>",
            ["Section", "Value"],
            [[pdf_paragraph(Paragraph, "Source", styles["Normal"]), pdf_paragraph(Paragraph, "Auto", styles["Normal"])]],
            [1.0 * inch, 2.0 * inch],
            styles=styles,
            colors=colors,
            table_cls=Table,
            table_style_cls=TableStyle,
            paragraph_cls=Paragraph,
            spacer_cls=Spacer,
            header_bg=colors.lightgrey,
            normal_style=styles["Normal"],
            row_backgrounds=[colors.whitesmoke],
        )

        self.assertEqual(5, len(story))
        self.assertIsInstance(story[0], Spacer)
        self.assertIsInstance(story[-1], Table)

        empty_story = []
        append_detail_table(
            empty_story,
            "Empty",
            "No rows",
            ["A"],
            [],
            [1.0 * inch],
            styles=styles,
            colors=colors,
            table_cls=Table,
            table_style_cls=TableStyle,
            paragraph_cls=Paragraph,
            spacer_cls=Spacer,
            header_bg=colors.lightgrey,
            normal_style=styles["Normal"],
        )

        self.assertEqual([], empty_story)


if __name__ == "__main__":
    unittest.main()
