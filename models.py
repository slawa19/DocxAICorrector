from dataclasses import dataclass


@dataclass
class ParagraphUnit:
    text: str
    role: str


@dataclass
class DocumentBlock:
    paragraphs: list["ParagraphUnit"]

    @property
    def text(self) -> str:
        return "\n\n".join(paragraph.text for paragraph in self.paragraphs)
