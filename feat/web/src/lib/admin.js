import { inject, onBeforeUnmount } from 'vue';
import { useRoute, useRouter } from 'vue-router';
export function useParams() {
  const route = useRoute(),
    router = useRouter();
  return (changes, replace = false) => {
    const query = { ...route.query, ...changes };
    for (const [key, value] of Object.entries(query))
      if (value == null || value === '') delete query[key];
    return router[replace ? 'replace' : 'push']({ path: route.path, query });
  };
}
export function useLeaveGuard(handler) {
  const register = inject('registerLeaveGuard', null);
  const remove = register?.(handler);
  onBeforeUnmount(() => remove?.());
}
// Recoverable CF submission acknowledgement outlives the module; no credentials live here.
export const cfMemory = {
  scope: null,
  statuses: [],
  excluded: [],
  input: '',
  contest: '',
  kind: 'problems',
  mode: 'any_submission',
  job: null,
  submission: null,
  recheck: false,
};
export const adminFilters = {};
