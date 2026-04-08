from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speech2text_site import (
    TranscriptSegment,
    _compose_transcript,
    _parse_interactive_segments,
)


class TranscriptParsingTests(unittest.TestCase):
    def test_parse_interactive_segments_with_speakers_and_timecodes(self) -> None:
        html_text = """
        <h6 class="speaker-button"><span class="speaker-name">Speaker 1</span></h6>
        <div class="time-string">00:00:01 - Hello world</div>
        <h6 class="speaker-button"><span class="speaker-name">Speaker 2</span></h6>
        <div class="time-string">00:00:03 - Second line</div>
        """

        segments = _parse_interactive_segments(html_text)

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].speaker, "Speaker 1")
        self.assertEqual(segments[0].timecode, "00:00:01")
        self.assertEqual(segments[0].text, "Hello world")
        self.assertEqual(segments[1].speaker, "Speaker 2")
        self.assertEqual(segments[1].text, "Second line")

    def test_compose_transcript_keeps_timecodes(self) -> None:
        transcript = _compose_transcript(
            [
                TranscriptSegment(
                    speaker="Speaker 1",
                    timecode="00:00:01",
                    text="Hello world",
                ),
                TranscriptSegment(
                    speaker="Speaker 2",
                    timecode="00:00:03",
                    text="Second line",
                ),
            ],
            include_timecodes=True,
        )

        self.assertEqual(
            transcript,
            "[00:00:01] Speaker 1: Hello world\n[00:00:03] Speaker 2: Second line",
        )


if __name__ == "__main__":
    unittest.main()
