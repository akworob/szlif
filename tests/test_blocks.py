import unittest

from szlif_core.blocks import split_blocks

PARAGRAPH = "Pierwszy akapit ma tutaj dość dużo słów, żeby model mógł go spokojnie przepisać bez kłopotu."
SECOND = "Drugi akapit także ma wystarczająco wiele słów, aby trafić do przepisania przez model językowy."


def rejoin(blocks):
    return "".join(b["tekst"] + b["odstep"] for b in blocks)


class Blocks(unittest.TestCase):
    def test_layout_rebuilds_exactly(self):
        for text in ["Tytuł\n\n%s\n\n- punkt jeden\n- punkt dwa\n\n%s\n" % (PARAGRAPH, SECOND),
                     "\n\n%s\n \n\n%s" % (PARAGRAPH, SECOND), PARAGRAPH, ""]:
            with self.subTest(text=text[:20]):
                self.assertEqual(rejoin(split_blocks(text)), text)

    def test_headings_lists_and_short_lines_kept(self):
        text = "Tytuł artykułu\n\n%s\n\n- punkt jeden\n- punkt dwa\n\n%s" % (PARAGRAPH, SECOND)
        self.assertEqual([b["przepisz"] for b in split_blocks(text)], [False, True, False, True])

    def test_numbered_list_kept(self):
        text = "1. " + PARAGRAPH + "\n2. " + SECOND
        self.assertEqual([b["przepisz"] for b in split_blocks(text)], [False])

    def test_block_text_has_no_trailing_space(self):
        blocks = split_blocks(PARAGRAPH + "  \n\n" + SECOND + "\n")
        self.assertEqual([b["tekst"] for b in blocks], [PARAGRAPH, SECOND])
        self.assertEqual([b["odstep"] for b in blocks], ["  \n\n", "\n"])


if __name__ == "__main__":
    unittest.main()
