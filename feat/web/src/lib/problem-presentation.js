// Display rules only: these categories never change a stored tag, filter key or rating.
const CATEGORY_NAMES = {
  strategy: '基础与策略',
  graph: '搜索与图论',
  dp: '动态规划',
  structure: '数据结构',
  math: '数学与数论',
  string: '字符串',
  geometry: '计算几何',
  other: '其他 / 尚未归类',
};
const CATEGORY_TONES = {
  strategy: 'orange',
  graph: 'blue',
  dp: 'purple',
  structure: 'cyan',
  math: 'yellow',
  string: 'green',
  geometry: 'pink',
  other: 'neutral',
};
// Exact aliases include CF source labels and the existing Chinese taxonomy IDs.
const ALIASES = {
  strategy: `基础算法与技巧|基础与策略|implementation|模拟|simulation|sortings|sorting|排序|binary search|binary_search|二分|二分查找|ternary search|ternary_search|三分|greedy|贪心|constructive algorithms|construction|构造|brute force|enumeration|枚举|暴力枚举|暴力|two pointers|two_pointers|双指针|sliding_window|滑动窗口|prefix_sum|前缀和|difference_array|差分|discretization|离散化|divide and conquer|divide_conquer|分治|meet-in-the-middle|meet_in_middle|折半搜索|bitmasks|bitmask|位掩码|bit_operations|位运算|backtracking|回溯搜索|expression parsing|expression_parsing|表达式解析|randomized_algorithms|随机化算法`,
  graph: `图论与树|搜索与图论|graphs|图|图论|trees|树|树上算法|搜索|dfs and similar|dfs|深度优先搜索|bfs|广度优先搜索|dijkstra|bellman_ford|Bellman-Ford|floyd|zero_one_bfs|0-1 BFS|topological_sort|拓扑排序|minimum_spanning_tree|最小生成树|scc|强连通分量|bridges|桥|articulation_points|割点|2-sat|two_sat|bipartite_matching|二分图匹配|graph matchings|matchings|flows|max_flow|最大流|min_cost_flow|最小费用流|网络流|lca|最近公共祖先|heavy_light_decomposition|树链剖分|tree_diameter|树的直径|tree_centroid|树的重心|centroid_decomposition|点分治|dsu_on_tree|树上启发式合并|euler_tour|欧拉序|functional_graph|基环树|shortest paths|最短路|dfs/bfs|pending_search|pending_graphs|pending_shortest_paths|pending_trees`,
  dp: `动态规划|dp|linear_dp|线性DP|knapsack_dp|背包DP|背包|interval_dp|区间DP|tree_dp|树形DP|bitmask_dp|状压DP|状态压缩DP|digit_dp|数位DP|probability_dp|概率DP|expectation_dp|期望DP|counting_dp|计数DP|rerooting_dp|换根DP|dp_optimization|DP优化|lis|最长上升子序列|grid_dp|网格DP|pending_dp`,
  structure: `数据结构|data structures|dsu|并查集|weighted_dsu|带权并查集|fenwick_tree|树状数组|segment_tree|线段树|lazy_segment_tree|懒标记线段树|persistent_segment_tree|可持久化线段树|sparse_table|ST表|priority_queue|优先队列|堆|monotonic_stack|单调栈|monotonic_queue|单调队列|balanced_tree|平衡树|sqrt_decomposition|分块|mo_algorithm|莫队|trie|字典树|hash_table|哈希表|pending_data_structures`,
  math: `数学与数论|math|数学|number theory|数论|combinatorics|组合|组合数学|probabilities|概率|概率与期望|期望|games|博弈论|matrices|矩阵|gcd|最大公约数|extended_gcd|扩展欧几里得|modular_inverse|模逆元|fast_power|快速幂|sieve|素数筛|prime_factorization|质因数分解|chinese remainder theorem|crt|中国剩余定理|combinatorial_counting|组合计数|inclusion_exclusion|容斥原理|stars_and_bars|隔板法|matrix_exponentiation|矩阵快速幂|gaussian_elimination|高斯消元|fft|快速傅里叶变换|ntt|快速数论变换|linearity_of_expectation|期望线性性|nim_game|Nim博弈|sg_function|SG函数|linear_recurrence|线性递推|pending_combinatorics|pending_games|pending_math|pending_matrices|pending_number_theory|pending_probabilities`,
  string: `字符串|strings|string suffix structures|字符串后缀结构|hashing|哈希|pending_hashing|kmp|z_function|Z函数|string_hash|字符串哈希|ac_automaton|AC自动机|suffix_array|后缀数组|suffix_automaton|后缀自动机|manacher|palindromic_tree|回文自动机|pending_strings`,
  geometry: `计算几何|geometry|几何|cross_product|叉积|convex_hull|凸包|rotating_calipers|旋转卡壳|sweep_line|扫描线|pending_geometry`,
};
const aliasKey = (value) =>
  String(value)
    .trim()
    .toLowerCase()
    .replace(/·待细化$/, '')
    .replace(/[_\s]+/g, ' ');
const categoryByAlias = new Map();
for (const [category, aliases] of Object.entries(ALIASES))
  for (const alias of aliases.split('|')) categoryByAlias.set(aliasKey(alias), category);

function tagLabel(tag) {
  if (typeof tag === 'string') return tag.trim();
  if (!tag || typeof tag !== 'object' || Array.isArray(tag)) return '';
  return (
    [tag.name_zh, tag.name, tag.label, tag.id]
      .find((value) => typeof value === 'string' && value.trim())
      ?.trim() || ''
  );
}

export function algorithmCategory(tag) {
  const candidates =
    typeof tag === 'object' && tag
      ? [
          tag.id,
          tagLabel(tag),
          typeof tag.category === 'object' ? tag.category?.name : tag.category,
        ]
      : [tag];
  const category =
    candidates
      .filter((value) => typeof value === 'string')
      .map((value) => categoryByAlias.get(aliasKey(value)))
      .find(Boolean) || 'other';
  return { category, name: CATEGORY_NAMES[category], tone: CATEGORY_TONES[category] };
}

export function normalizeTags(tags) {
  let values = tags;
  if (typeof values === 'string') {
    const value = values.trim();
    if (value.startsWith('[')) {
      try {
        values = JSON.parse(value);
      } catch {
        values = value;
      }
    }
    if (typeof values === 'string') values = values.split(/[,，;；、]/);
  }
  if (!Array.isArray(values)) values = values && typeof values === 'object' ? [values] : [];
  const seen = new Set();
  return values.flatMap((raw) => {
    const label = tagLabel(raw);
    const id = raw && typeof raw === 'object' ? raw.id : undefined;
    const key = typeof id === 'string' || typeof id === 'number' ? String(id) : label;
    if (!label || seen.has(key)) return [];
    seen.add(key);
    return [{ key, label, raw, ...algorithmCategory(raw) }];
  });
}

function numericRating(value) {
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  if (typeof value === 'string' && !/^\d+(?:\.\d+)?$/.test(value.trim())) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}
const color = (tone) => `var(--problem-color-${tone})`;

export function difficultyPresentation(problem = {}, platform = '') {
  const source = String(platform || problem.platform || '').toLowerCase();
  const raw = Object.hasOwn(problem, 'problem_rating') ? problem.problem_rating : problem.rating;
  const value = numericRating(raw);
  const unknown = {
    tone: 'neutral',
    color: color('neutral'),
    value: null,
    label: '难度未知',
    title: '尚无可确认的题目难度',
    system: 'unknown',
  };
  if (source === 'luogu') {
    const native = problem.native_difficulty;
    const hasNativeName = typeof native?.name === 'string' && native.name.trim();
    const hasNativeId =
      (typeof native?.id === 'number' && Number.isInteger(native.id) && native.id >= 0) ||
      (typeof native?.id === 'string' && /^\d+$/.test(native.id));
    // Historical recommendation/submission rows have a textual grade but no
    // native taxonomy object. Keep that evidence without guessing a native ID.
    const legacy = typeof raw === 'string' ? raw.trim() : '';
    if (
      !hasNativeName &&
      !hasNativeId &&
      /\p{Letter}/u.test(legacy) &&
      !/[\x00-\x1f\x7f]/.test(legacy) &&
      !Number.isFinite(Number(legacy)) &&
      !/^(?:null|undefined|nan|[+-]?infinity)$/i.test(legacy)
    ) {
      return {
        ...unknown,
        label: `难度 ${legacy}`,
        title: '洛谷历史记录原始难度 · 尚未关联原生分类，不推测等级 ID',
        system: 'luogu_legacy',
      };
    }
    return {
      ...unknown,
      system: 'luogu',
      label: native?.name || '难度待收录',
      title: '洛谷原生难度',
    };
  }
  if (source === 'codeforces') {
    if (value === null || value <= 0) return unknown;
    const tone =
      value < 1200
        ? 'gray'
        : value < 1400
          ? 'green'
          : value < 1600
            ? 'cyan'
            : value < 1900
              ? 'blue'
              : value < 2100
                ? 'purple'
                : value < 2400
                  ? 'orange'
                  : 'red';
    return {
      tone,
      color: color(tone),
      value,
      label: `难度 ${value}`,
      title: `Codeforces 题目 Rating · ${value}`,
      system: 'codeforces',
    };
  }
  if (source === 'atcoder' && problem.difficulty_source === 'atcoder_problems') {
    if (value === null) return { ...unknown, title: 'AtCoder Problems 尚无估计难度' };
    const tone =
      value < 400
        ? 'gray'
        : value < 800
          ? 'brown'
          : value < 1200
            ? 'green'
            : value < 1600
              ? 'cyan'
              : value < 2000
                ? 'blue'
                : value < 2400
                  ? 'yellow'
                  : value < 2800
                    ? 'orange'
                    : 'red';
    const experimental = problem.difficulty_is_experimental === true;
    return {
      tone,
      color: color(tone),
      value,
      label: `难度 ${value}`,
      title: `AtCoder Problems 估计难度 · ${value}${experimental ? ' · 实验模型' : ''}`,
      system: 'atcoder_problems',
    };
  }
  // Older AtCoder rows may contain contest points. Preserve their value without
  // assigning them an estimated-difficulty colour or a CF rating meaning.
  if (source === 'atcoder' && value === null) return unknown;
  const label = typeof raw === 'string' ? raw.trim() : value === null ? '' : String(value);
  if (!label || (typeof raw === 'string' && /^(?:null|undefined|nan|[+-]?infinity)$/i.test(label)))
    return unknown;
  if (value === null && /^[+-]?[\d.]+(?:e[+-]?\d+)?$/i.test(label)) return unknown;
  return {
    ...unknown,
    value,
    label: `难度 ${label}`,
    title:
      source === 'atcoder'
        ? 'AtCoder 原始难度值 · 来源未标注，未套用估计难度色阶'
        : `${source || '原平台'} 原始难度 · 未换算为 CF Rating`,
    system: 'native',
  };
}
