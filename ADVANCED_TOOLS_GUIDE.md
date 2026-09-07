# Advanced Tools Guide - Web Automation & Archive Handling

Complete guide for Jarvis's new advanced capabilities.

## 🚀 New Tools Overview

Jarvis now includes **3 powerful new tools**:

1. **🌐 Web Browser Automation** - Interact with JavaScript-heavy websites
2. **📥 File Downloader** - Download files from the internet
3. **📦 Archive Extractor** - Extract ZIP, TAR, 7Z files

**Total Tools**: 11 (was 8)

## 🌐 Web Browser Automation

### Tool: `browse_website_interactive`

**Purpose:** Browse and interact with modern JavaScript-heavy websites using Playwright (headless browser).

**When to Use:**
- Website requires JavaScript to load content
- Single Page Applications (SPAs)
- Dynamic content that doesn't work with BeautifulSoup
- Need to click buttons or interact with elements
- AJAX/React/Vue.js websites

### Usage

**Basic browsing:**
```python
browse_website_interactive("https://example.com")
```

**With actions:**
```python
browse_website_interactive("https://example.com", "click login button")
browse_website_interactive("https://example.com", "scroll down")
```

### Examples

#### Example 1: Browse SPA Website
```
User: "Browse https://react-app.com and get the content"
Jarvis: Uses playwright to load JavaScript and extract content
```

#### Example 2: Interactive Actions
```
User: "Go to https://example.com and click the menu button"
Jarvis: Opens headless browser, clicks button, returns result
```

### Supported Actions

| Action | Syntax | Description |
|--------|--------|-------------|
| Click | "click button text" | Clicks element with text |
| Scroll Down | "scroll down" | Scrolls to bottom |
| Scroll Up | "scroll up" | Scrolls to top |
| Load Page | (no action) | Just loads and extracts |

### Technical Details

**Engine:** Playwright (Chromium headless)
**Timeout:** 30 seconds page load, 10 seconds network idle
**Approval:** Required (security popup)
**Output:** Cleaned text content (max 5000 chars)

### Installation

First time setup:
```bash
pip install playwright
playwright install chromium
```

### Advantages over fetch_webpage

| Feature | fetch_webpage | browse_website_interactive |
|---------|---------------|---------------------------|
| JavaScript | ❌ No | ✅ Yes |
| Dynamic Content | ❌ No | ✅ Yes |
| Interactions | ❌ No | ✅ Yes (basic) |
| Speed | ✅ Fast | ⚠️ Slower |
| Resources | ✅ Light | ⚠️ Heavy |

**Rule of Thumb:** Try `fetch_webpage` first, use `browse_website_interactive` if content is missing.

## 📥 File Downloader

### Tool: `download_file`

**Purpose:** Download files from URLs and save to workspace.

**When to Use:**
- Download documents (PDF, DOCX, etc.)
- Download images
- Download archives (ZIP, TAR, etc.)
- Download datasets
- Download any file from internet

### Usage

**Auto filename:**
```python
download_file("https://example.com/document.pdf")
```

**Custom filename:**
```python
download_file("https://example.com/file", "my_document.pdf")
```

### Examples

#### Example 1: Download PDF
```
User: "Download the file from https://example.com/manual.pdf"
Jarvis: Downloads to workspace/manual.pdf
```

#### Example 2: Custom Name
```
User: "Download https://example.com/img.jpg and save as photo.jpg"
Jarvis: Downloads to workspace/photo.jpg
```

#### Example 3: Download Archive
```
User: "Download https://github.com/repo/archive.zip"
Jarvis: Downloads archive.zip
User: "Now extract it"
Jarvis: Extracts using extract_archive tool
```

### Features

- ✅ **Auto-detects filename** from URL
- ✅ **Streaming download** for large files
- ✅ **Progress tracking** (internal)
- ✅ **Size limit**: 100MB max
- ✅ **Timeout**: 60 seconds
- ✅ **Approval required**

### Technical Details

**Method:** requests with streaming
**Location:** Always saves to `workspace/`
**Headers:** Includes user agent
**Chunk size:** 8192 bytes

### Supported Formats

All file types supported:
- 📄 Documents: PDF, DOCX, TXT, etc.
- 🖼️ Images: JPG, PNG, GIF, etc.
- 📦 Archives: ZIP, TAR, 7Z, RAR, etc.
- 🎵 Media: MP3, MP4, etc.
- 💾 Data: CSV, JSON, XML, etc.

## 📦 Archive Extractor

### Tool: `extract_archive`

**Purpose:** Extract compressed archive files in workspace.

**When to Use:**
- Extract downloaded ZIP files
- Unpack TAR archives
- Extract 7Z files
- Access files inside compressed archives

### Usage

**Simple extraction:**
```python
extract_archive("download.zip")
# Extracts to workspace/download/
```

**Custom destination:**
```python
extract_archive("archive.tar.gz", "my_folder")
# Extracts to workspace/my_folder/
```

### Examples

#### Example 1: Extract ZIP
```
User: "Extract the file project.zip"
Jarvis: Extracts to workspace/project/
       Shows list of extracted files
```

#### Example 2: Extract TAR.GZ
```
User: "Extract archive.tar.gz to extracted_data"
Jarvis: Extracts to workspace/extracted_data/
```

#### Example 3: Download and Extract
```
User: "Download https://example.com/data.zip and extract it"
Jarvis: 
  1. Downloads data.zip
  2. Extracts to workspace/data/
  3. Lists all extracted files
```

### Supported Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| ZIP | `.zip` | Most common |
| TAR | `.tar` | Unix archive |
| TAR.GZ | `.tar.gz`, `.tgz` | Compressed TAR |
| TAR.BZ2 | `.tar.bz2` | BZ2 compressed |
| 7-Zip | `.7z` | High compression |

**Note:** RAR support requires `unrar` utility installed on system.

### Features

- ✅ **Auto-detects format** from extension
- ✅ **Creates extraction folder** automatically
- ✅ **Lists extracted files** (first 10 shown)
- ✅ **Safe extraction** (workspace only)
- ✅ **Approval required**

### Technical Details

**Libraries:**
- ZIP: Python's `zipfile` (built-in)
- TAR: Python's `tarfile` (built-in)
- 7Z: `py7zr` library

**Location:** Extracts to `workspace/{archive_name}/` by default

### Security

- ✅ Path validation (prevents zip bombs)
- ✅ Workspace sandboxing
- ✅ File count limits (implicit)
- ✅ User approval required

## 🎯 Combined Workflows

### Workflow 1: Download and Extract
```
User: "Download the archive from https://example.com/data.zip 
       and extract it"

Jarvis:
1. download_file("https://example.com/data.zip")
   → workspace/data.zip
2. extract_archive("data.zip")
   → workspace/data/
3. list_directory("data")
   → Shows extracted files
```

### Workflow 2: Web Scraping Complex Site
```
User: "Get all text from https://react-app.com"

Jarvis:
1. Try fetch_webpage (fails - JavaScript needed)
2. Use browse_website_interactive
   → Loads with Playwright
   → Returns full content
```

### Workflow 3: Automated Data Collection
```
User: "Download https://api.com/dataset.zip, extract it, 
       and read the data.csv file"

Jarvis:
1. download_file("https://api.com/dataset.zip")
2. extract_archive("dataset.zip")
3. read_file("dataset/data.csv")
   → Shows CSV content
```

## 📊 Tool Comparison

### Web Tools

| Tool | Best For | Speed | JavaScript | Interaction |
|------|----------|-------|------------|-------------|
| `search_web` | Finding info | ⚡ Fast | N/A | No |
| `fetch_webpage` | Static HTML | ⚡ Fast | ❌ No | No |
| `browse_website_interactive` | Dynamic sites | 🐌 Slow | ✅ Yes | ✅ Basic |

### File Tools

| Tool | Purpose | Direction |
|------|---------|-----------|
| `read_file` | Read local file | Local → Jarvis |
| `write_file` | Create file | Jarvis → Local |
| `download_file` | Get from internet | Internet → Local |
| `extract_archive` | Unpack archive | Archive → Files |

## 🔧 Installation & Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright (First Time)

```bash
pip install playwright
playwright install chromium
```

This downloads Chromium browser (~100MB).

### 3. Verify Installation

```bash
python -c "from playwright.sync_api import sync_playwright; print('✓ Playwright ready')"
python -c "import py7zr; print('✓ 7z support ready')"
```

## 💡 Usage Tips

### For Web Automation

1. **Try Simple First:** Use `fetch_webpage` before `browse_website_interactive`
2. **Be Specific:** Describe actions clearly ("click login button")
3. **Wait for Load:** Tool automatically waits for network idle
4. **Check Content:** If content is empty, site might need interaction

### For Downloads

1. **Check URL:** Ensure it's a direct download link
2. **Size Matters:** Files over 100MB will be rejected
3. **Naming:** Let Jarvis auto-detect filename or specify custom
4. **Verify:** Use `list_directory` to confirm download

### For Archives

1. **Format Check:** Ensure archive format is supported
2. **Space Check:** Large archives need disk space
3. **List First:** Use `list_directory` before extracting
4. **Clean Up:** Delete archive after extraction if not needed

## 🐛 Troubleshooting

### Playwright Issues

**Error:** "Playwright not installed"
```bash
pip install playwright
playwright install chromium
```

**Error:** "Chromium not found"
```bash
playwright install chromium
```

**Error:** "Page timeout"
- Website is slow or unreachable
- Try increasing timeout (code modification)
- Check internet connection

### Download Issues

**Error:** "File too large"
- Solution: Files limited to 100MB for safety
- Alternative: Download manually

**Error:** "Download timeout"
- Solution: Slow connection or large file
- Try again or check URL

**Error:** "Invalid URL"
- Solution: Ensure URL starts with http:// or https://

### Archive Issues

**Error:** "Unsupported format"
- Solution: Use supported formats (.zip, .tar, .gz, .7z)
- Alternative: Extract manually

**Error:** "Corrupted archive"
- Solution: Re-download the file
- Check: Use `read_file` to verify download

**Error:** "Permission denied"
- Solution: Check workspace permissions
- Alternative: Run as administrator

## 📈 Performance

### Resource Usage

| Tool | CPU | RAM | Disk | Network |
|------|-----|-----|------|---------|
| `browse_website_interactive` | High | ~200MB | ~100MB (cache) | High |
| `download_file` | Low | ~50MB | File size | High |
| `extract_archive` | Medium | ~100MB | 2x archive | None |

### Speed Benchmarks

| Operation | Time |
|-----------|------|
| Simple webpage | 1-3 seconds |
| JavaScript page | 5-10 seconds |
| Download 10MB | 2-5 seconds |
| Extract ZIP (100 files) | 1-2 seconds |

## 🔒 Security

### Approval Requirements

All new tools require user approval:
- ✅ Web automation - Shows URL and actions
- ✅ File download - Shows URL and destination
- ✅ Archive extraction - Shows archive and destination

### Safety Measures

**Web Automation:**
- Headless mode (no GUI)
- Network isolation
- Timeout protection

**File Download:**
- Size limits (100MB)
- Workspace only
- URL validation

**Archive Extraction:**
- Path validation
- Workspace only
- Format verification

## 🎓 Examples Gallery

### Example 1: GitHub Repository Download

```
User: "Download the latest release from 
       https://github.com/user/repo/archive/main.zip 
       and extract it"

Steps:
1. download_file("https://github.com/user/repo/archive/main.zip")
2. extract_archive("main.zip", "repo")
3. list_directory("repo")
```

### Example 2: Scrape Dynamic Content

```
User: "Get the product list from https://shop.com/products"

Jarvis tries:
1. fetch_webpage (fails - JavaScript needed)
2. browse_website_interactive (success)
   → Returns product list
```

### Example 3: Download Dataset

```
User: "Download https://data.gov/dataset.csv 
       and show me the first 10 lines"

Steps:
1. download_file("https://data.gov/dataset.csv")
2. read_file("dataset.csv")
   → Shows content
```

### Example 4: Multi-Archive Project

```
User: "I have project.zip, extract it and list all Python files"

Steps:
1. extract_archive("project.zip")
2. list_directory("project")
3. (Jarvis identifies .py files)
```

## 🔮 Future Enhancements

### Planned Features

- [ ] **Advanced browser actions** (form filling, login)
- [ ] **Resume downloads** (interrupted downloads)
- [ ] **Archive creation** (create ZIP from files)
- [ ] **Progress bars** (download/extraction progress)
- [ ] **Parallel downloads** (multiple files)
- [ ] **Cloud storage** (Google Drive, Dropbox)

### Possible Tools

- [ ] `create_archive` - Create ZIP/TAR files
- [ ] `download_video` - YouTube video downloader
- [ ] `screenshot_webpage` - Capture page screenshot
- [ ] `convert_file` - Format conversion (PDF→TXT)

## 📝 Summary

### New Capabilities

✅ **Web Automation**: Browse JavaScript websites  
✅ **File Downloads**: Get files from internet  
✅ **Archive Handling**: Extract compressed files  

### Total Tools

**11 Tools Now:**
1. execute_terminal_command
2. read_file
3. write_file
4. append_to_file
5. list_directory
6. delete_file
7. search_web
8. fetch_webpage
9. **browse_website_interactive** 🆕
10. **download_file** 🆕
11. **extract_archive** 🆕

### Quick Commands

**Installation:**
```bash
pip install -r requirements.txt
playwright install chromium
```

**Testing:**
```bash
python gui.py
# Try: "Download https://example.com/file.zip and extract it"
```

---

**"Sir, advanced capabilities are now online. Web automation and file handling systems operational."** 🤖⚡
