import { algorithmCategory } from './problem-presentation.js';

// The picker translates labels for display. Its selected values are Codeforces source tags.
const names = new Map([
  ['*special', '特殊题'],
  ['2-sat', '二元可满足性（2-SAT）'],
  ['binary search', '二分查找'],
  ['bitmasks', '位掩码'],
  ['brute force', '暴力枚举'],
  ['chinese remainder theorem', '中国剩余定理'],
  ['combinatorics', '组合数学'],
  ['communication', '通信题'],
  ['constructive algorithms', '构造'],
  ['data structures', '数据结构'],
  ['dfs and similar', '深度优先搜索及类似算法'],
  ['divide and conquer', '分治'],
  ['dp', '动态规划'],
  ['dsu', '并查集'],
  ['expression parsing', '表达式解析'],
  ['fft', '快速傅里叶变换'],
  ['flows', '网络流'],
  ['games', '博弈论'],
  ['geometry', '计算几何'],
  ['graph matchings', '图匹配'],
  ['graphs', '图论'],
  ['greedy', '贪心'],
  ['hashing', '哈希'],
  ['implementation', '模拟'],
  ['interactive', '交互题'],
  ['math', '数学'],
  ['matrices', '矩阵'],
  ['meet-in-the-middle', '折半搜索'],
  ['number theory', '数论'],
  ['probabilities', '概率与期望'],
  ['schedules', '调度'],
  ['shortest paths', '最短路'],
  ['sortings', '排序'],
  ['string suffix structures', '字符串后缀结构'],
  ['strings', '字符串'],
  ['ternary search', '三分查找'],
  ['trees', '树上算法'],
  ['two pointers', '双指针'],
]);

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
