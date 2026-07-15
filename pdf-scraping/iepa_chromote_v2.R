################################################################################
# IEPA DocuWare PDF Downloader — chromote v3
#
# Install:
#   install.packages(c("chromote", "rvest", "httr", "stringr", "fs", "jsonlite"))
#
# If Chrome not found:
#   chromote::local_chrome_version("latest-stable", binary = "chrome")
################################################################################

library(chromote)
library(rvest)
library(httr)
library(stringr)
library(fs)
library(jsonlite)

# ------------------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------------------

agency_ids    <- c("170000063561")
output_dir    <- "iepa_pdfs"
EXPLORER_BASE <- "https://webapps.illinois.gov/EPA/DocumentExplorer/Documents/Index"
DOCUWARE_HOST <- "https://docuware7.illinois.gov"

page_load_wait <- 8
download_wait  <- 6

# ------------------------------------------------------------------------------
# LAUNCH CHROME
# The "Target position can only be set for new windows" error is a Chrome/
# chromote compatibility bug. Fix: launch the Chromote browser object manually
# with --window-size set, which prevents Chrome from trying to set position
# on the initial target.
# ------------------------------------------------------------------------------

launch_browser <- function() {
  cm <- Chromote$new(
    browser = Chrome$new(
      args = c(
        "--headless",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1280,900",
        "--disable-extensions",
        "--disable-background-networking",
        "--no-first-run",
        "--no-default-browser-check"
      )
    )
  )
  # Create session from the browser object directly
  b <- cm$new_session()
  message("Chrome launched OK")
  b
}

# ------------------------------------------------------------------------------
# STEP 1: Scrape Document Explorer
# ------------------------------------------------------------------------------

get_category_links <- function(agency_id) {
  url  <- paste0(EXPLORER_BASE, "/", agency_id)
  message("Scraping: ", url)
  resp <- httr::GET(url, httr::timeout(30))
  page <- read_html(httr::content(resp, "text", encoding = "UTF-8"))
  rows <- page %>% html_nodes("table tbody tr")
  
  results <- lapply(rows, function(row) {
    cells     <- row %>% html_nodes("td")
    link_node <- cells[[1]] %>% html_node("a")
    if (is.null(link_node) || length(cells) < 2) return(NULL)
    list(
      category        = html_text(link_node, trim = TRUE),
      doc_count       = suppressWarnings(as.integer(html_text(cells[[2]], trim = TRUE))),
      integration_url = html_attr(link_node, "href")
    )
  })
  Filter(Negate(is.null), results)
}

# ------------------------------------------------------------------------------
# STEP 2: Navigate and wait for JS to render
# ------------------------------------------------------------------------------

navigate_and_wait <- function(b, url, wait_secs = page_load_wait) {
  b$Page$navigate(url, wait_ = FALSE)
  b$Page$loadEventFired(wait_ = TRUE, timeout = 30)
  Sys.sleep(wait_secs)
}

# ------------------------------------------------------------------------------
# STEP 3: Count document rows in rendered result list
# ------------------------------------------------------------------------------

get_doc_row_count <- function(b) {
  js <- '
    (function() {
      var selectors = [
        ".dw-result-list-item",
        ".result-list-item",
        "[data-doc-id]",
        ".document-row",
        "tbody tr[class*=document]",
        "tbody tr[class*=result]",
        ".dw-list-item",
        "dw-result-list-item"
      ];
      for (var i = 0; i < selectors.length; i++) {
        var els = document.querySelectorAll(selectors[i]);
        if (els.length > 0) {
          return JSON.stringify({selector: selectors[i], count: els.length});
        }
      }
      var rows = Array.from(document.querySelectorAll("tbody tr")).filter(function(r) {
        return r.querySelectorAll("td").length > 2;
      });
      if (rows.length > 0) {
        return JSON.stringify({selector: "tbody tr (filtered)", count: rows.length});
      }
      return JSON.stringify({selector: null, count: 0});
    })()
  '
  result <- b$Runtime$evaluate(js, wait_ = TRUE)$result$value
  tryCatch(fromJSON(result), error = function(e) list(selector = NULL, count = 0))
}

# ------------------------------------------------------------------------------
# STEP 4: Click the nth document row
# ------------------------------------------------------------------------------

click_doc_row <- function(b, selector, index) {
  js <- sprintf('
    (function() {
      var els = document.querySelectorAll("%s");
      if (els.length > %d) { els[%d].click(); return "clicked"; }
      return "not found";
    })()
  ', selector, index, index)
  b$Runtime$evaluate(js, wait_ = TRUE)$result$value
}

# ------------------------------------------------------------------------------
# STEP 5: Trigger download with Ctrl+Alt+D
# ------------------------------------------------------------------------------

trigger_download_from_viewer <- function(b) {
  Sys.sleep(page_load_wait)
  
  current_url <- b$Runtime$evaluate("window.location.href", wait_ = TRUE)$result$value
  message("    Viewer URL: ", substr(current_url, 1, 80), "...")
  message("    Sending Ctrl+Alt+D...")
  
  b$Input$dispatchKeyEvent(type = "keyDown", key = "Control", code = "ControlLeft", modifiers = 0L,  wait_ = TRUE)
  b$Input$dispatchKeyEvent(type = "keyDown", key = "Alt",     code = "AltLeft",     modifiers = 2L,  wait_ = TRUE)
  b$Input$dispatchKeyEvent(type = "keyDown", key = "d",       code = "KeyD",        modifiers = 3L,  wait_ = TRUE)
  b$Input$dispatchKeyEvent(type = "keyUp",   key = "d",       code = "KeyD",        modifiers = 3L,  wait_ = TRUE)
  b$Input$dispatchKeyEvent(type = "keyUp",   key = "Alt",     code = "AltLeft",     modifiers = 2L,  wait_ = TRUE)
  b$Input$dispatchKeyEvent(type = "keyUp",   key = "Control", code = "ControlLeft", modifiers = 0L,  wait_ = TRUE)
  
  message("    Ctrl+Alt+D sent. Waiting ", download_wait, "s...")
  Sys.sleep(download_wait)
}

# ------------------------------------------------------------------------------
# MAIN DOWNLOAD LOOP
# ------------------------------------------------------------------------------

download_category <- function(b, integration_url, cat_dir, expected_count) {
  abs_cat_dir <- path_abs(cat_dir)
  message("  Output folder: ", abs_cat_dir)
  
  # Intercept network to capture FileDownload URLs
  download_urls <- character(0)
  b$Network$enable(wait_ = TRUE)
  b$Network$requestWillBeSent(function(params) {
    url <- params$request$url
    if (str_detect(url, "FileDownload|targetFileType=PDF")) {
      message("  [Network] Captured: ", substr(url, 1, 80))
      download_urls <<- c(download_urls, url)
    }
  })
  
  # Load result list
  message("  Loading result page...")
  navigate_and_wait(b, integration_url)
  
  row_info <- get_doc_row_count(b)
  message("  Doc rows: ", row_info$count, " (selector: ", row_info$selector, ")")
  
  if (row_info$count == 0) {
    message("  No rows found. Saving HTML for inspection...")
    html <- b$Runtime$evaluate("document.documentElement.outerHTML", wait_ = TRUE)$result$value
    writeLines(html, path(cat_dir, "result_page.html"))
    b$Network$disable(wait_ = TRUE)
    return(invisible(0))
  }
  
  n <- min(row_info$count, expected_count)
  message("  Clicking ", n, " document(s)...")
  
  for (i in seq_len(n)) {
    message("\n  [Doc ", i, "/", n, "]")
    
    if (i > 1) navigate_and_wait(b, integration_url, wait_secs = 5)
    
    click_result <- click_doc_row(b, row_info$selector, i - 1)
    message("    Click: ", click_result)
    if (click_result != "clicked") { message("    Skipping."); next }
    
    trigger_download_from_viewer(b)
    Sys.sleep(2)
  }
  
  b$Network$disable(wait_ = TRUE)
  
  # Save captured URLs as PDFs using browser cookies
  if (length(download_urls) > 0) {
    message("\n  Captured ", length(download_urls), " URL(s) — downloading...")
    
    cookies_raw <- b$Network$getCookies(wait_ = TRUE)$cookies
    cookie_str  <- ""
    if (!is.null(cookies_raw) && nrow(cookies_raw) > 0) {
      cookie_str <- paste(paste0(cookies_raw$name, "=", cookies_raw$value), collapse = "; ")
    }
    
    for (i in seq_along(unique(download_urls))) {
      url  <- unique(download_urls)[[i]]
      dest <- path(cat_dir, sprintf("doc_%03d.pdf", i))
      message("  [", i, "] ", basename(dest))
      resp <- httr::GET(
        url,
        httr::timeout(120),
        httr::add_headers(Accept = "application/pdf,application/octet-stream,*/*",
                          Cookie = cookie_str),
        httr::write_disk(dest, overwrite = TRUE)
      )
      if (httr::http_error(resp)) {
        message("    FAILED (", httr::status_code(resp), ")")
      } else {
        message("    OK: ", dest)
      }
      Sys.sleep(1)
    }
  } else {
    message("  No download URLs captured.")
  }
  
  saved <- dir_ls(cat_dir, glob = "*.pdf")
  message("  PDFs saved: ", length(saved))
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------

dir_create(output_dir, recurse = TRUE)

message("Launching Chrome...")
b <- launch_browser()

on.exit({
  tryCatch(b$parent$close(), error = function(e) NULL)
  message("Chrome closed.")
}, add = TRUE)

for (aid in agency_ids) {
  message("\n========================================")
  message("Agency ID: ", aid)
  message("========================================")
  
  cats <- tryCatch(get_category_links(aid), error = function(e) {
    message("Error: ", e$message); NULL
  })
  if (is.null(cats) || length(cats) == 0) { message("No categories."); next }
  message("Categories: ", paste(sapply(cats, `[[`, "category"), collapse = ", "))
  
  for (cat in cats) {
    message("\n--- ", cat$category, " (", cat$doc_count, " docs) ---")
    safe_cat <- str_replace_all(cat$category, "[^A-Za-z0-9_-]", "_")
    cat_dir  <- path(output_dir, aid, safe_cat)
    dir_create(cat_dir, recurse = TRUE)
    
    tryCatch(
      download_category(b, cat$integration_url, cat_dir, cat$doc_count),
      error = function(e) message("Error: ", e$message)
    )
    Sys.sleep(2)
  }
}

message("\nDone. Files in: ", path_abs(output_dir))