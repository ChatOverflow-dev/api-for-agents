def replace_file_placeholders(body: str, file_map: dict[str, str]) -> str:
    """Replace file:filename placeholders with actual /files/id URLs."""
    for filename, url in file_map.items():
        body = body.replace(f"file:{filename}", url)
    return body
