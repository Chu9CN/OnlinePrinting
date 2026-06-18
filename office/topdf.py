import os
import sys
import pythoncom
import win32com.client

def convert_to_pdf(input_path, output_pdf_path=None):
    """
    自动根据文件扩展名调用 Word 或 Excel 将文档转换为 PDF。
    
    Args:
        input_path (str): 输入文件路径（支持 .doc, .docx, .xls, .xlsx）
        output_pdf_path (str, optional): 输出 PDF 路径，默认与输入文件同目录同名 .pdf
    
    Returns:
        str: 生成的 PDF 文件路径
    
    Raises:
        ValueError: 不支持的文件类型
        Exception: 转换过程中的其他错误
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"文件不存在: {input_path}")
    
    ext = os.path.splitext(input_path)[1].lower()
    
    if output_pdf_path is None:
        output_pdf_path = os.path.splitext(input_path)[0] + ".pdf"
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)

    pythoncom.CoInitialize()
    try:
        if ext in ['.doc', '.docx']:
            # 使用 Word 转换
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False  # 不显示 Word 界面
            doc = None
            try:
                doc = word.Documents.Open(input_path)
                # 17 代表 wdFormatPDF
                doc.SaveAs(output_pdf_path, FileFormat=17)
            finally:
                if doc:
                    doc.Close()
                word.Quit()
        
        elif ext in ['.xls', '.xlsx']:
            # 使用 Excel 转换
            excel = win32com.client.Dispatch("Excel.Application")
            excel.Visible = False
            wb = None
            try:
                wb = excel.Workbooks.Open(input_path)
                # 0 代表 xlTypePDF
                wb.ExportAsFixedFormat(0, output_pdf_path)
            finally:
                if wb:
                    wb.Close(False)
                excel.Quit()
        
        else:
            raise ValueError(f"不支持的文件类型: {ext}，仅支持 .doc, .docx, .xls, .xlsx")
    finally:
        pythoncom.CoUninitialize()
    
    return output_pdf_path


if __name__ == "__main__":
    # 示例用法
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else None
        try:
            print(f"开始转换: {input_file} -> {output_file or '自动'}", file=sys.stderr)
            result = convert_to_pdf(input_file, output_file)
            print(f"转换成功: {result}")
        except Exception as e:
            print(f"转换失败: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        print("用法: python convert_to_pdf.py <输入文件> [输出PDF文件]")