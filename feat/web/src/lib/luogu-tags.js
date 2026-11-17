// Preserve the native IDs, category order and parent hierarchy supplied by Luogu.
export function luoguTagCategories(taxonomy = {}) {
  const tags = [
    ...new Map(
      (taxonomy.tags || []).map((tag) => [
        String(tag.id),
        {
          ...tag,
          id: String(tag.id),
          type: String(tag.type),
          name: tag.name.trim(),
        },
      ]),
    ).values(),
  ];
  const types = new Map((taxonomy.tag_types || []).map((type) => [String(type.id), type]));
  for (const tag of tags)
    if (!types.has(tag.type)) types.set(tag.type, { id: tag.type, name: '其他标签' });
  return [...types.values()]
    .sort((a, b) => (a.order ?? Infinity) - (b.order ?? Infinity))
    .map((type) => {
      const items = tags.filter((tag) => tag.type === String(type.id));
      const byId = new Map(items.map((tag) => [tag.id, tag]));
      const children = new Map();
      for (const tag of items) {
        const parent = tag.parent == null ? null : String(tag.parent);
        if (!children.has(parent)) children.set(parent, []);
        children.get(parent).push(tag);
      }
      const seen = new Set(),
        groups = [];
      function group(root) {
        if (seen.has(root.id)) return;
        const members = [];
        function visit(tag) {
          if (seen.has(tag.id)) return;
          seen.add(tag.id);
          members.push(tag);
          for (const child of children.get(tag.id) || []) visit(child);
        }
        visit(root);
        groups.push({ id: root.id, name: root.name, items: members });
      }
      for (const tag of items) if (tag.parent == null || !byId.has(String(tag.parent))) group(tag);
      // A stale or malformed parent link must not hide tags or loop indefinitely.
      for (const tag of items) group(tag);
      return { id: String(type.id), name: type.name, groups };
    })
    .filter((category) => category.groups.length);
}

export function searchLuoguTags(categories, query) {
  const keyword = query.normalize('NFKC').trim().toLocaleLowerCase();
  if (!keyword) return categories;
  const matches = (value) => String(value).normalize('NFKC').toLocaleLowerCase().includes(keyword);
  return categories
    .map((category) => ({
      ...category,
      groups: category.groups
        .map((group) => ({
          ...group,
          items:
            matches(category.name) || matches(group.name)
              ? group.items
              : group.items.filter((tag) => matches(tag.name) || matches(tag.id)),
        }))
        .filter((group) => group.items.length),
    }))
    .filter((category) => category.groups.length);
}
