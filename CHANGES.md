# Changelog

## 2026-06-05

### Fix: FAL (Free Art License) in Bild-Lizenz-Whitelist + NC/ND-Ausschluss

**Auslöser:** Kalibrier-Harness-Fund (`Elephant_feces_in_the_wildlife.jpg`, Lizenz FAL,
steht im echten Klexikon-Artikel — wurde fälschlich auf reject gesetzt).

**Änderungen:**
- `_is_free_license()` in `generate_articles.py` — FAL/LAL/Free Art/Licence Art Libre ergänzt;
  CC-BY-NC / CC-BY-ND explizit ausgeschlossen (NC = nicht kommerziell, ND = keine Bearbeitung)
- `patch_article_images_v1.py` — `_is_free_license()` neu hinzugefügt (fehlte); Lizenzfilter-Schritt
  nach `fetch_commons_metadata()` ergänzt (fehlte trotz Doku-Behauptung)
- `test_image_safety_filter.py` — `LICENSE_KEYWORDS` um FAL-Strings erweitert;
  NC/ND-Ausschluss in `_is_free_license()`-Wrapper ergänzt
- `WISSEN_BILDER.md` — Stufe-1-Beschreibung aktualisiert, Doku-Fehler korrigiert,
  Kalibrier-Notiz Pilot Elefant ergänzt

**Neue Whitelist:** CC0, CC-BY (alle Versionen), CC-BY-SA (alle Versionen), FAL, LAL, LAL-1.2, LAL-1.3, Public Domain
**Ausgeschlossen:** CC-BY-NC-*, CC-BY-ND-* (und alle NC/ND-Kombinationen)
