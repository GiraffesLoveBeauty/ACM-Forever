import { createDefaultTheme } from './theme-colors.js';

// Categories can exist before their first template is published.
export const TEMPLATE_CATEGORIES = Object.freeze([
  { id: 'default', name: '默认' },
  { id: 'arknights', name: '明日方舟' },
  { id: 'genshin', name: '原神' },
  { id: 'zenless', name: '绝区零' },
]);
export const DESIGN_TEMPLATES = Object.freeze([
  {
    id: 'original',
    category: 'default',
    name: '原有设计模板',
    description: '原有工业布局，支持现有全部配色。',
    preview: 'original',
  },
  {
    id: 'phase',
    category: 'arknights',
    name: '相变信号',
    description: '放射图盘、四色轨道与三角标记。',
    preview: 'phase',
  },
  {
    id: 'angel-city',
    category: 'arknights',
    name: '天使之城',
    description: '雾白城市、钴蓝坐标与镜像等高线。',
    preview: 'angel-city',
  },
]);
export const normalizeTemplate = (value) =>
  DESIGN_TEMPLATES.some((template) => template.id === value) ? value : 'original';
export const templateLabel = (value) =>
  DESIGN_TEMPLATES.find((template) => template.id === normalizeTemplate(value)).name;
export const themeStorageKey = (template) =>
  normalizeTemplate(template) === 'original'
    ? 'acm.theme.v1'
    : `acm.theme.${normalizeTemplate(template)}.v1`;
export const libraryStorageKey = (template) =>
  normalizeTemplate(template) === 'original'
    ? 'acm.theme.library.v1'
    : `acm.theme.${normalizeTemplate(template)}.library.v1`;
export function templateTheme(template) {
  const theme = createDefaultTheme();
  if (normalizeTemplate(template) === 'phase') {
    theme.light.colors = {
      primary: '#202629',
      background: '#e7e8e5',
      surface: '#f8f9f6',
      accent: '#d5f500',
    };
    theme.light.overrides.hero = '#151a1d';
    theme.dark.colors = {
      primary: '#e4ece9',
      background: '#101619',
      surface: '#1d2529',
      accent: '#d5f500',
    };
    theme.dark.overrides.hero = '#11171a';
  }
  if (normalizeTemplate(template) === 'angel-city') {
    theme.light.colors = {
      primary: '#202729',
      background: '#f0f3f1',
      surface: '#fcfdfc',
      accent: '#155bd8',
    };
    theme.light.overrides.hero = '#edf2ef';
    theme.dark.colors = {
      primary: '#e4eeef',
      background: '#111b22',
      surface: '#1b2831',
      accent: '#74adff',
    };
    theme.dark.overrides.hero = '#182630';
  }
  return theme;
}
