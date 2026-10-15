"""内存中的虚构 PDF 样本；没有真实简历，也不保存上传文件。"""

from io import BytesIO
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, ArrayObject, NumberObject, DecodedStreamObject


def resume_pdf(*texts, password=None):
    """创建含中文文字层的最小 PDF，用来验证真实解析器而不是函数替身。"""
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=595, height=842)
        if text is None:
            continue
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type0"), NameObject("/BaseFont"): NameObject("/STSong-Light"),
            NameObject("/Encoding"): NameObject("/UniGB-UCS2-H"),
            NameObject("/DescendantFonts"): ArrayObject([DictionaryObject({
                NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/CIDFontType0"),
                NameObject("/BaseFont"): NameObject("/STSong-Light"),
                NameObject("/DW"): NumberObject(1000)})])})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 750 Td <{text.encode('utf-16-be').hex()}> Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if password:
        writer.encrypt(password)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
