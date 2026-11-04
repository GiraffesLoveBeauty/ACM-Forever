CREATE TABLE IF NOT EXISTS wiki_categories (
 id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES wiki_categories(id),
 name TEXT NOT NULL, name_key TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 sort_order INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, deleted_at INTEGER);
CREATE UNIQUE INDEX IF NOT EXISTS wiki_category_names ON wiki_categories(COALESCE(parent_id,0),name_key) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS wiki_settings (
 id INTEGER PRIMARY KEY CHECK(id=1), default_category_id INTEGER REFERENCES wiki_categories(id),
 navigation_version INTEGER NOT NULL DEFAULT 1, public_content_version INTEGER NOT NULL DEFAULT 1);
INSERT OR IGNORE INTO wiki_settings(id) VALUES(1);
CREATE TABLE IF NOT EXISTS wiki_pages (
 id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, category_id INTEGER NOT NULL REFERENCES wiki_categories(id),
 published_revision_id INTEGER, draft_revision_id INTEGER, version INTEGER NOT NULL DEFAULT 1,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS wiki_pages_category ON wiki_pages(category_id);
CREATE TABLE IF NOT EXISTS wiki_revisions (
 id INTEGER PRIMARY KEY, page_id INTEGER NOT NULL REFERENCES wiki_pages(id), parent_revision_id INTEGER REFERENCES wiki_revisions(id),
 title TEXT NOT NULL, body TEXT NOT NULL, metadata TEXT NOT NULL, author TEXT NOT NULL,
 created_at INTEGER NOT NULL, published_at INTEGER, hidden INTEGER NOT NULL DEFAULT 0 CHECK(hidden IN(0,1)));
CREATE INDEX IF NOT EXISTS wiki_revision_page ON wiki_revisions(page_id,id);
CREATE TABLE IF NOT EXISTS wiki_search (
 page_id INTEGER PRIMARY KEY REFERENCES wiki_pages(id), title TEXT NOT NULL, aliases TEXT NOT NULL, tags TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wiki_category_operations (
 id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
 created_at INTEGER NOT NULL, restored_at INTEGER);
CREATE TABLE IF NOT EXISTS wiki_delete_previews (
 token TEXT PRIMARY KEY, actor TEXT NOT NULL, category_id INTEGER NOT NULL, fingerprint TEXT NOT NULL, expires_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS wiki_requests (
 actor TEXT NOT NULL, operation TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL, response TEXT NOT NULL,
 PRIMARY KEY(actor,operation,key));
CREATE TABLE IF NOT EXISTS markdown_assets (
 id TEXT PRIMARY KEY, storage_name TEXT NOT NULL UNIQUE, content_type TEXT NOT NULL,
 size INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 owner TEXT NOT NULL, document_type TEXT NOT NULL, document_id INTEGER NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS markdown_asset_references (
 asset_id TEXT NOT NULL REFERENCES markdown_assets(id), document_type TEXT NOT NULL, document_id INTEGER NOT NULL,
 revision_id INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(asset_id,document_type,document_id,revision_id));
CREATE TRIGGER IF NOT EXISTS wiki_parent_insert BEFORE INSERT ON wiki_categories
 WHEN NEW.parent_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM wiki_categories WHERE id=NEW.parent_id AND parent_id IS NULL AND deleted_at IS NULL)
 BEGIN SELECT RAISE(ABORT,'wiki_invalid_parent'); END;
CREATE TRIGGER IF NOT EXISTS wiki_parent_update BEFORE UPDATE OF parent_id ON wiki_categories
 WHEN NEW.parent_id=NEW.id OR NEW.parent_id IS NOT NULL AND (EXISTS(SELECT 1 FROM wiki_categories WHERE parent_id=NEW.id AND deleted_at IS NULL) OR NOT EXISTS(SELECT 1 FROM wiki_categories WHERE id=NEW.parent_id AND parent_id IS NULL AND deleted_at IS NULL))
 BEGIN SELECT RAISE(ABORT,'wiki_invalid_parent'); END;
CREATE TRIGGER IF NOT EXISTS wiki_page_category_insert BEFORE INSERT ON wiki_pages
 WHEN NOT EXISTS(SELECT 1 FROM wiki_categories c JOIN wiki_categories p ON p.id=c.parent_id WHERE c.id=NEW.category_id AND c.deleted_at IS NULL AND p.deleted_at IS NULL)
 BEGIN SELECT RAISE(ABORT,'wiki_invalid_category'); END;
CREATE TRIGGER IF NOT EXISTS wiki_page_category_update BEFORE UPDATE OF category_id ON wiki_pages
 WHEN NOT EXISTS(SELECT 1 FROM wiki_categories c JOIN wiki_categories p ON p.id=c.parent_id WHERE c.id=NEW.category_id AND c.deleted_at IS NULL AND p.deleted_at IS NULL)
 BEGIN SELECT RAISE(ABORT,'wiki_invalid_category'); END;
CREATE TRIGGER IF NOT EXISTS wiki_page_pointers BEFORE UPDATE OF published_revision_id,draft_revision_id ON wiki_pages
 WHEN NEW.published_revision_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM wiki_revisions WHERE id=NEW.published_revision_id AND page_id=NEW.id AND published_at IS NOT NULL AND hidden=0)
 OR NEW.draft_revision_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM wiki_revisions WHERE id=NEW.draft_revision_id AND page_id=NEW.id)
 BEGIN SELECT RAISE(ABORT,'wiki_invalid_revision'); END;
CREATE TRIGGER IF NOT EXISTS wiki_revision_immutable BEFORE UPDATE OF page_id,parent_revision_id,title,body,metadata,author,created_at ON wiki_revisions
 BEGIN SELECT RAISE(ABORT,'wiki_revision_immutable'); END;
