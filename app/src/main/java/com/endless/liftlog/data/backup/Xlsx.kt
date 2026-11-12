package com.endless.liftlog.data.backup

import org.xml.sax.Attributes
import org.xml.sax.InputSource
import org.xml.sax.helpers.DefaultHandler
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.temporal.ChronoUnit
import java.util.Locale
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream
import javax.xml.parsers.SAXParserFactory
import kotlin.math.roundToLong

/**
 * Minimal, dependency-free .xlsx (Office Open XML spreadsheet) writer and reader.
 *
 * The writer produces plain workbooks (bold frozen header row, date formats, column widths) that
 * open in Excel, Google Sheets, LibreOffice and Numbers. The reader understands what those apps
 * write back after editing (shared strings, inline strings, numbers, booleans), so a backup can be
 * edited and restored.
 */
object Xlsx {

    sealed interface Cell {
        data class Text(val value: String) : Cell
        data class Number(val value: Double) : Cell
        data class DateTime(val value: LocalDateTime) : Cell
        data class Day(val value: LocalDate) : Cell
        data object Empty : Cell
    }

    data class Column(val header: String, val width: Double = 14.0)

    data class Sheet(val name: String, val columns: List<Column>, val rows: List<List<Cell>>)

    /** A cell read back from a file. [number] is set for numeric cells (dates are numbers too). */
    data class Value(val text: String, val number: Double?)

    data class ReadSheet(val name: String, val rows: List<List<Value?>>)

    class FormatException(message: String) : IOException(message)

    // ---------------------------------------------------------------- writing

    fun write(sheets: List<Sheet>, out: OutputStream) {
        require(sheets.isNotEmpty()) { "A workbook needs at least one sheet" }
        val zip = ZipOutputStream(out)
        fun entry(name: String, content: String) {
            zip.putNextEntry(ZipEntry(name))
            zip.write(content.toByteArray(Charsets.UTF_8))
            zip.closeEntry()
        }
        entry("[Content_Types].xml", contentTypes(sheets.size))
        entry("_rels/.rels", ROOT_RELS)
        entry("xl/workbook.xml", workbook(sheets))
        entry("xl/_rels/workbook.xml.rels", workbookRels(sheets.size))
        entry("xl/styles.xml", STYLES)
        sheets.forEachIndexed { index, sheet -> entry("xl/worksheets/sheet${index + 1}.xml", worksheet(sheet)) }
        zip.finish()
        zip.flush()
    }

    fun toBytes(sheets: List<Sheet>): ByteArray = ByteArrayOutputStream().also { write(sheets, it) }.toByteArray()

    private const val STYLE_HEADER = 1
    private const val STYLE_DATETIME = 2
    private const val STYLE_DATE = 3

    private fun worksheet(sheet: Sheet): String = buildString {
        append(XML_HEADER)
        append("<worksheet xmlns=\"$NS_MAIN\" xmlns:r=\"$NS_REL\">")
        append("<sheetViews><sheetView workbookViewId=\"0\">")
        append("<pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\"/>")
        append("</sheetView></sheetViews>")
        append("<sheetFormatPr defaultRowHeight=\"15\"/>")
        if (sheet.columns.isNotEmpty()) {
            append("<cols>")
            sheet.columns.forEachIndexed { i, column ->
                append("<col min=\"${i + 1}\" max=\"${i + 1}\" width=\"${column.width}\" customWidth=\"1\"/>")
            }
            append("</cols>")
        }
        append("<sheetData>")
        val header = sheet.columns.map { Cell.Text(it.header) }
        (listOf(header) + sheet.rows).forEachIndexed { rowIndex, cells ->
            val r = rowIndex + 1
            append("<row r=\"$r\">")
            cells.forEachIndexed { col, cell ->
                val ref = columnName(col) + r
                val headerStyle = if (rowIndex == 0) " s=\"$STYLE_HEADER\"" else ""
                when (cell) {
                    is Cell.Text -> if (cell.value.isNotEmpty()) {
                        append("<c r=\"$ref\" t=\"inlineStr\"$headerStyle><is><t xml:space=\"preserve\">")
                        append(escape(cell.value))
                        append("</t></is></c>")
                    }
                    is Cell.Number -> if (cell.value.isFinite()) {
                        append("<c r=\"$ref\"$headerStyle><v>${formatNumber(cell.value)}</v></c>")
                    }
                    is Cell.DateTime ->
                        append("<c r=\"$ref\" s=\"$STYLE_DATETIME\"><v>${formatNumber(toSerial(cell.value))}</v></c>")
                    is Cell.Day ->
                        append("<c r=\"$ref\" s=\"$STYLE_DATE\"><v>${formatNumber(toSerial(cell.value.atStartOfDay()))}</v></c>")
                    Cell.Empty -> Unit
                }
            }
            append("</row>")
        }
        append("</sheetData>")
        append("</worksheet>")
    }

    private fun workbook(sheets: List<Sheet>): String = buildString {
        append(XML_HEADER)
        append("<workbook xmlns=\"$NS_MAIN\" xmlns:r=\"$NS_REL\"><sheets>")
        val used = mutableSetOf<String>()
        sheets.forEachIndexed { i, sheet ->
            var name = sanitizeSheetName(sheet.name).ifEmpty { "Sheet${i + 1}" }
            while (!used.add(name.lowercase())) name = name.take(28) + "_${i + 1}"
            append("<sheet name=\"${escape(name)}\" sheetId=\"${i + 1}\" r:id=\"rId${i + 1}\"/>")
        }
        append("</sheets></workbook>")
    }

    private fun workbookRels(count: Int): String = buildString {
        append(XML_HEADER)
        append("<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">")
        for (i in 1..count) {
            append("<Relationship Id=\"rId$i\" ")
            append("Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" ")
            append("Target=\"worksheets/sheet$i.xml\"/>")
        }
        append("<Relationship Id=\"rId${count + 1}\" ")
        append("Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" ")
        append("Target=\"styles.xml\"/>")
        append("</Relationships>")
    }

    private fun contentTypes(count: Int): String = buildString {
        append(XML_HEADER)
        append("<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">")
        append("<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>")
        append("<Default Extension=\"xml\" ContentType=\"application/xml\"/>")
        append("<Override PartName=\"/xl/workbook.xml\" ")
        append("ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>")
        append("<Override PartName=\"/xl/styles.xml\" ")
        append("ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>")
        for (i in 1..count) {
            append("<Override PartName=\"/xl/worksheets/sheet$i.xml\" ")
            append("ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>")
        }
        append("</Types>")
    }

    private const val XML_HEADER = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
    private const val NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    private const val NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

    private const val ROOT_RELS = XML_HEADER +
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">" +
        "<Relationship Id=\"rId1\" " +
        "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" " +
        "Target=\"xl/workbook.xml\"/></Relationships>"

    // Style 0: default, 1: bold header on a light fill, 2: date + time, 3: date.
    private const val STYLES = XML_HEADER +
        "<styleSheet xmlns=\"$NS_MAIN\">" +
        "<numFmts count=\"2\">" +
        "<numFmt numFmtId=\"164\" formatCode=\"yyyy-mm-dd hh:mm\"/>" +
        "<numFmt numFmtId=\"165\" formatCode=\"yyyy-mm-dd\"/>" +
        "</numFmts>" +
        "<fonts count=\"2\">" +
        "<font><sz val=\"11\"/><name val=\"Calibri\"/><family val=\"2\"/></font>" +
        "<font><b/><sz val=\"11\"/><name val=\"Calibri\"/><family val=\"2\"/></font>" +
        "</fonts>" +
        "<fills count=\"3\">" +
        "<fill><patternFill patternType=\"none\"/></fill>" +
        "<fill><patternFill patternType=\"gray125\"/></fill>" +
        "<fill><patternFill patternType=\"solid\"><fgColor rgb=\"FFE8ECF4\"/><bgColor indexed=\"64\"/></patternFill></fill>" +
        "</fills>" +
        "<borders count=\"1\"><border><left/><right/><top/><bottom/><diagonal/></border></borders>" +
        "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>" +
        "<cellXfs count=\"4\">" +
        "<xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/>" +
        "<xf numFmtId=\"0\" fontId=\"1\" fillId=\"2\" borderId=\"0\" xfId=\"0\" applyFont=\"1\" applyFill=\"1\"/>" +
        "<xf numFmtId=\"164\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyNumberFormat=\"1\"/>" +
        "<xf numFmtId=\"165\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyNumberFormat=\"1\"/>" +
        "</cellXfs>" +
        "<cellStyles count=\"1\"><cellStyle name=\"Normal\" xfId=\"0\" builtinId=\"0\"/></cellStyles>" +
        "</styleSheet>"

    // ---------------------------------------------------------------- reading

    private const val MAX_TOTAL_BYTES = 64L * 1024 * 1024

    fun read(input: InputStream): List<ReadSheet> {
        val parts = unzip(input)
        val workbook = parts["xl/workbook.xml"]
            ?: throw FormatException("This isn't an Excel (.xlsx) file")
        val relationships = parts["xl/_rels/workbook.xml.rels"]?.let(::parseRelationships).orEmpty()
        val sharedStrings = parts["xl/sharedStrings.xml"]?.let(::parseSharedStrings).orEmpty()
        return parseWorkbookSheets(workbook).map { (name, relId) ->
            val target = relationships[relId]
                ?: throw FormatException("Sheet \"$name\" is missing from the file")
            val path = resolvePart(target)
            val xml = parts[path] ?: throw FormatException("Sheet \"$name\" is missing from the file")
            ReadSheet(name, parseWorksheet(xml, sharedStrings))
        }
    }

    private fun unzip(input: InputStream): Map<String, ByteArray> {
        val parts = mutableMapOf<String, ByteArray>()
        var total = 0L
        val buffer = ByteArray(16 * 1024)
        ZipInputStream(input).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                if (entry.isDirectory) continue
                val bytes = ByteArrayOutputStream()
                while (true) {
                    val n = zip.read(buffer)
                    if (n < 0) break
                    total += n
                    if (total > MAX_TOTAL_BYTES) throw FormatException("The file is too large")
                    bytes.write(buffer, 0, n)
                }
                parts[entry.name.removePrefix("/")] = bytes.toByteArray()
            }
        }
        if (parts.isEmpty()) throw FormatException("This isn't an Excel (.xlsx) file")
        return parts
    }

    private fun resolvePart(target: String): String = when {
        target.startsWith("/") -> target.removePrefix("/")
        else -> "xl/" + target.removePrefix("./")
    }

    private fun parse(xml: ByteArray, handler: DefaultHandler) {
        val factory = SAXParserFactory.newInstance()
        factory.isNamespaceAware = true
        runCatching { factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true) }
        runCatching { factory.setFeature("http://xml.org/sax/features/external-general-entities", false) }
        try {
            factory.newSAXParser().parse(InputSource(ByteArrayInputStream(xml)), handler)
        } catch (e: Exception) {
            throw FormatException("The file is damaged or not a valid .xlsx file")
        }
    }

    private fun Attributes.byLocalName(name: String): String? {
        for (i in 0 until length) {
            val local = getLocalName(i).ifEmpty { getQName(i).substringAfter(':') }
            if (local == name) return getValue(i)
        }
        return null
    }

    private fun localName(localName: String, qName: String) = localName.ifEmpty { qName.substringAfter(':') }

    private fun parseWorkbookSheets(xml: ByteArray): List<Pair<String, String>> {
        val sheets = mutableListOf<Pair<String, String>>()
        parse(xml, object : DefaultHandler() {
            override fun startElement(uri: String, localName: String, qName: String, attributes: Attributes) {
                if (localName(localName, qName) == "sheet") {
                    val name = attributes.byLocalName("name") ?: return
                    val id = attributes.byLocalName("id") ?: return
                    sheets += name to id
                }
            }
        })
        return sheets
    }

    private fun parseRelationships(xml: ByteArray): Map<String, String> {
        val map = mutableMapOf<String, String>()
        parse(xml, object : DefaultHandler() {
            override fun startElement(uri: String, localName: String, qName: String, attributes: Attributes) {
                if (localName(localName, qName) == "Relationship") {
                    val id = attributes.byLocalName("Id") ?: return
                    val target = attributes.byLocalName("Target") ?: return
                    map[id] = target
                }
            }
        })
        return map
    }

    private fun parseSharedStrings(xml: ByteArray): List<String> {
        val strings = mutableListOf<String>()
        parse(xml, object : DefaultHandler() {
            private val current = StringBuilder()
            private var inText = false
            private var phoneticDepth = 0

            override fun startElement(uri: String, localName: String, qName: String, attributes: Attributes) {
                when (localName(localName, qName)) {
                    "si" -> current.setLength(0)
                    "rPh" -> phoneticDepth++
                    "t" -> inText = phoneticDepth == 0
                }
            }

            override fun endElement(uri: String, localName: String, qName: String) {
                when (localName(localName, qName)) {
                    "si" -> strings += current.toString()
                    "rPh" -> phoneticDepth--
                    "t" -> inText = false
                }
            }

            override fun characters(ch: CharArray, start: Int, length: Int) {
                if (inText) current.append(ch, start, length)
            }
        })
        return strings
    }

    private fun parseWorksheet(xml: ByteArray, sharedStrings: List<String>): List<List<Value?>> {
        val rows = sortedMapOf<Int, MutableMap<Int, Value>>()
        parse(xml, object : DefaultHandler() {
            private var rowIndex = -1
            private var nextColumn = 0
            private var cellColumn = 0
            private var cellType = ""
            private var inCell = false
            private var collecting = false
            private var inInlineString = false
            private val value = StringBuilder()
            private val inline = StringBuilder()

            override fun startElement(uri: String, localName: String, qName: String, attributes: Attributes) {
                when (localName(localName, qName)) {
                    "row" -> {
                        rowIndex = attributes.byLocalName("r")?.toIntOrNull()?.minus(1) ?: (rowIndex + 1)
                        nextColumn = 0
                    }
                    "c" -> {
                        inCell = true
                        cellType = attributes.byLocalName("t").orEmpty()
                        cellColumn = attributes.byLocalName("r")?.let(::columnIndex) ?: nextColumn
                        nextColumn = cellColumn + 1
                        value.setLength(0)
                        inline.setLength(0)
                    }
                    "v" -> if (inCell) collecting = true
                    "is" -> if (inCell) inInlineString = true
                    "t" -> if (inInlineString) collecting = true
                }
            }

            override fun endElement(uri: String, localName: String, qName: String) {
                when (localName(localName, qName)) {
                    "v", "t" -> collecting = false
                    "is" -> inInlineString = false
                    "c" -> {
                        inCell = false
                        cellValue()?.let { rows.getOrPut(rowIndex) { mutableMapOf() }[cellColumn] = it }
                    }
                }
            }

            override fun characters(ch: CharArray, start: Int, length: Int) {
                if (!collecting) return
                if (inInlineString) inline.append(ch, start, length) else value.append(ch, start, length)
            }

            private fun cellValue(): Value? {
                val raw = value.toString()
                return when (cellType) {
                    "s" -> raw.trim().toIntOrNull()?.let { sharedStrings.getOrNull(it) }?.let { Value(it, null) }
                    "inlineStr" -> Value(inline.toString(), null)
                    "str", "e", "d" -> Value(raw, null)
                    "b" -> Value(if (raw.trim() == "1") "TRUE" else "FALSE", null)
                    else -> if (raw.isEmpty()) null else Value(raw, raw.trim().toDoubleOrNull())
                }?.takeIf { it.text.isNotEmpty() || it.number != null }
            }
        })
        if (rows.isEmpty()) return emptyList()
        val lastRow = rows.lastKey()
        return (0..lastRow).map { r ->
            val cells = rows[r] ?: return@map emptyList()
            val lastColumn = cells.keys.maxOrNull() ?: return@map emptyList()
            (0..lastColumn).map { cells[it] }
        }
    }

    // ---------------------------------------------------------------- helpers

    private val EXCEL_EPOCH: LocalDateTime = LocalDateTime.of(1899, 12, 30, 0, 0)

    fun toSerial(dateTime: LocalDateTime): Double =
        ChronoUnit.SECONDS.between(EXCEL_EPOCH, dateTime) / 86_400.0

    fun fromSerial(serial: Double): LocalDateTime =
        EXCEL_EPOCH.plusSeconds((serial * 86_400.0).roundToLong())

    fun columnName(index: Int): String {
        var n = index + 1
        val sb = StringBuilder()
        while (n > 0) {
            val rem = (n - 1) % 26
            sb.append('A' + rem)
            n = (n - 1) / 26
        }
        return sb.reverse().toString()
    }

    fun columnIndex(cellRef: String): Int? {
        var result = 0
        var any = false
        for (ch in cellRef) {
            if (ch.isLetter()) {
                result = result * 26 + (ch.uppercaseChar() - 'A' + 1)
                any = true
            } else {
                break
            }
        }
        return if (any) result - 1 else null
    }

    private fun formatNumber(value: Double): String =
        if (value == Math.rint(value) && kotlin.math.abs(value) < 1e15) {
            value.toLong().toString()
        } else {
            String.format(Locale.US, "%.10f", value).trimEnd('0').trimEnd('.')
        }

    private fun sanitizeSheetName(name: String): String =
        name.filterNot { it in "[]:*?/\\" }.trim().take(31)

    private fun escape(text: String): String {
        val sb = StringBuilder(text.length)
        for (ch in text) {
            when {
                ch == '&' -> sb.append("&amp;")
                ch == '<' -> sb.append("&lt;")
                ch == '>' -> sb.append("&gt;")
                ch == '"' -> sb.append("&quot;")
                ch == '\t' || ch == '\n' || ch == '\r' -> sb.append(ch)
                ch < ' ' || ch == '￾' || ch == '￿' -> Unit // not allowed in XML
                else -> sb.append(ch)
            }
        }
        return sb.toString()
    }
}
