import localizedNames from '../../../api/acm_api/codeforces-tags.zh.json' with { type: 'json' };
import { algorithmCategory } from './problem-presentation.js';

// The picker translates labels for display. Its selected values are Codeforces source tags.
const names = new Map(Object.entries(localizedNames));

const aliases = new Map([
  ['bitmasks', '位运算'],
  ['chinese remainder theorem', 'CRT 孙子定理'],
  ['constructive algorithms', '构造算法'],
  ['dfs and similar', '搜索 DFS'],
  ['implementation', '实现'],
  ['meet-in-the-middle', '折半枚举 MITM'],
  ['trees', '树形结构'],
]);

const categories = [
  {
    id: 'algorithm',
    name: '算法',
    groups: [
      ['strategy', '基础与策略'],
      ['graph', '搜索与图论'],
      ['dp', '动态规划'],
      ['structure', '数据结构'],
      ['string', '字符串'],
      ['geometry', '计算几何'],
    ],
  },
  { id: 'math', name: '数学', groups: [['math', '数学与数论']] },
  { id: 'special', name: '特殊题目', groups: [['special', '题目属性']] },
  { id: 'other', name: '其他', groups: [['other', '未归类标签']] },
];

export function codeforcesTagName(raw) {
  if (typeof raw !== 'string') return '';
  return names.get(raw.trim().toLowerCase()) || raw.trim();
}

function tagGroup(key) {
  if (key === 'interactive' || key === 'communication' || key === '*special') return 'special';
  if (key === 'schedules') return 'strategy';
  return algorithmCategory(key).category;
}

export function codeforcesTagCategories(tags = []) {
  const itemsByGroup = new Map();
  const seen = new Set();
  for (const raw of tags) {
    if (typeof raw !== 'string') continue;
    const id = raw.trim();
    const key = id.toLowerCase();
    if (!id || seen.has(key)) continue;
    seen.add(key);
    const group = tagGroup(key);
    if (!itemsByGroup.has(group)) itemsByGroup.set(group, []);
    itemsByGroup.get(group).push({
      id,
      name: codeforcesTagName(id),
      searchText: aliases.has(key) ? `${id} ${aliases.get(key)}` : id,
    });
  }
  return categories
    .map(({ id, name, groups }) => ({
      id,
      name,
      groups: groups
        .filter(([key]) => itemsByGroup.has(key))
        .map(([id, name]) => ({
          id,
          name,
          items: itemsByGroup.get(id).sort((a, b) => a.id.localeCompare(b.id, 'en')),
        })),
    }))
    .filter((category) => category.groups.length);
}
