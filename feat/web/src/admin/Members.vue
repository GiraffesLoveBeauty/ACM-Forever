<script setup>
import { useMemberProfiles } from '../composables/useMemberProfiles.js';
import { profileFields } from '../lib/member-profiles.js';
import { draftKey } from '../lib/member-profile-drafts.js';
import Pager from '../components/Pager.vue';
import MemberDetail from './MemberDetail.vue';
import MemberStatusDrawer from '../components/member-profiles/MemberStatusDrawer.vue';
import MemberProfileConflict from '../components/member-profiles/MemberProfileConflict.vue';
const {
  ready,
  route,
  update,
  filters,
  data,
  options,
  loading,
  loadError,
  editing,
  saving,
  message,
  storageError,
  storageWarnings,
  candidates,
  pendingOpen,
  drawerQQ,
  conflictQQ,
  records,
  drafts,
  dirty,
  pendingStatuses,
  drawerRecord,
  conflictRecord,
  localSummary,
  load,
  applyFilters,
  openDrawer,
  rememberDrawer,
  selectStatus,
  cancelDrawer,
  recover,
  discard,
  discardAll,
  stateLabel,
  permission,
  dirtyField,
  value,
  input,
  saveAll,
  check,
  merge,
  leaveEditing,
  flush,
} = useMemberProfiles();
</script>
<template>
  <MemberDetail v-if="route.query.qq_id" :key="route.query.qq_id" />
  <section v-else class="admin-panel member-profiles">
    <header class="member-profile-heading">
      <div>
        <h2>成员资料</h2>
        <p class="muted">真实姓名、成员身份与账号权限分别展示，权限在成员账号中管理。</p>
      </div>
      <button
        v-if="!editing"
        class="btn primary"
        :disabled="!ready || loading"
        @click="editing = true"
      >
        进入编辑模式
      </button>
    </header>
    <form class="filters profile-filters" @submit.prevent="applyFilters()">
      <label
        >关键词<input
          v-model="filters.search"
          type="search"
          placeholder="QQ、真实姓名、昵称或 OJ 账号"
      /></label>
      <label
        >学校<select v-model="filters.school" aria-label="学校">
          <option value="">全部学校</option>
          <option v-for="school in options.schools" :key="school" :value="school">
            {{ school }}
          </option>
          <option v-if="filters.school && !options.schools.includes(filters.school)">
            {{ filters.school }}
          </option>
        </select></label
      >
      <label
        >身份<select v-model="filters.status" aria-label="身份">
          <option value="">全部身份</option>
          <option v-for="status in options.statuses" :key="status" :value="status">
            {{ status }}
          </option>
          <option v-if="filters.status && !options.statuses.includes(filters.status)">
            {{ filters.status }}
          </option>
        </select></label
      >
      <button class="btn primary">搜索</button
      ><button type="button" class="btn" @click="applyFilters(true)">重置</button>
    </form>
    <div v-if="candidates.length" class="profile-notice">
      <span
        >发现 {{ candidates.length }} 条本地草稿 · 最近更新
        {{
          new Date(Math.max(...candidates.map((item) => item.record.updated_at))).toLocaleString()
        }}</span
      ><button class="btn" @click="recover">恢复草稿</button
      ><button class="btn" :disabled="saving" @click="discardAll">放弃本账号草稿</button>
    </div>
    <div v-if="editing" class="profile-edit-bar">
      <strong>编辑成员资料 · 已修改 {{ dirty.length }} 人</strong
      ><span :role="storageError ? 'alert' : 'status'">{{ localSummary }}</span>
      <div class="chips">
        <button class="btn primary" :disabled="saving || !dirty.length" @click="saveAll()">
          {{ saving ? '保存中…' : `保存全部（${dirty.length}）` }}</button
        ><button class="btn" @click="pendingOpen = !pendingOpen">查看待保存</button
        ><button class="btn" @click="leaveEditing">退出编辑，保留草稿</button
        ><button class="btn" :disabled="saving" @click="discardAll">放弃全部草稿</button>
      </div>
    </div>
    <div v-else-if="dirty.length" class="profile-notice">
      有 {{ dirty.length }} 人的未提交修改，当前显示服务端已保存资料。<button
        class="btn"
        @click="editing = true"
      >
        继续编辑
      </button>
    </div>
    <p v-if="message" role="status" class="profile-notice">{{ message }}</p>
    <p v-if="storageError && !editing" role="alert">{{ storageError }}</p>
    <div v-if="storageWarnings.length" role="alert">
      <p v-for="(warning, i) in storageWarnings" :key="i">
        草稿读取异常：{{ warning.message }}。可清空本账号本页草稿，未恢复的内容不会自动提交。
      </p>
      <button class="btn" :disabled="saving" @click="discardAll">清空本账号本页草稿</button>
    </div>
    <MemberProfileConflict
      v-if="conflictRecord?.current"
      :key="conflictRecord.qq_id + '-' + conflictRecord.current.profile_revision"
      :record="conflictRecord"
      :current="conflictRecord.current"
      @resolve="merge"
      @close="conflictQQ = null"
    />
    <section v-if="pendingOpen && records.length" class="profile-pending" aria-label="待保存成员">
      <h3>全部编辑成员（包含其他页和筛选条件）</h3>
      <article v-for="record in records" :key="draftKey(record)" class="list-item">
        <div>
          <b>{{ record.base.name }} · QQ {{ record.qq_id }}</b>
          <p>
            {{ stateLabel(record) }} · {{ Object.keys(record.changes).length }} 个字段{{
              record.drawer?.creating ? ' · 有未确认身份输入' : ''
            }}
          </p>
          <p v-if="record.error" role="alert">{{ record.error }}</p>
          <p v-for="(error, key) in record.fieldErrors" :key="key" role="alert">
            {{ profileFields[key] }}：{{ error }}
          </p>
        </div>
        <div class="chips">
          <button v-if="record.current" class="btn" @click="conflictQQ = record.qq_id">
            核对变化</button
          ><button v-else-if="record.state === 'uncertain'" class="btn" @click="check(record)">
            核对保存结果</button
          ><button
            v-else-if="Object.keys(record.changes).length && record.state !== 'blocked'"
            class="btn"
            :disabled="saving || record.state === 'saving'"
            @click="saveAll(record)"
          >
            保存此成员</button
          ><button
            class="btn"
            :disabled="record.state === 'saving'"
            @click="update({ search: record.qq_id, school: null, status: null, page: 1 })"
          >
            定位成员</button
          ><button v-if="record.drawer?.creating" class="btn" @click="drawerQQ = record.qq_id">
            继续身份输入</button
          ><button class="btn" :disabled="record.state === 'saving'" @click="discard(record)">
            放弃此草稿
          </button>
        </div>
      </article>
    </section>
    <p v-if="loading" role="status">正在加载成员资料…</p>
    <div v-else-if="loadError" role="alert">
      <p>成员资料加载失败：{{ loadError }}</p>
      <button class="btn" @click="load">重新加载</button>
    </div>
    <template v-else-if="data"
      ><p class="muted">共 {{ data.total }} 位成员 · 第 {{ data.page }} 页</p>
      <p v-if="!data.items.length">
        {{
          filters.search || filters.school || filters.status
            ? '没有符合条件的成员。请调整或重置筛选。'
            : '暂无成员资料。'
        }}
      </p>
      <div
        v-else
        class="table-wrap profile-table-wrap"
        tabindex="0"
        aria-label="成员资料表格，可横向滚动"
      >
        <table class="profile-table">
          <thead>
            <tr>
              <th>QQ</th>
              <th v-for="(label, key) in profileFields" :key="key">{{ label }}</th>
              <th>权限（只读）</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in data.items"
              :key="row.qq_id + '-' + row.account_epoch"
              :data-member="row.qq_id"
              :class="{
                'profile-row-dirty':
                  drafts[row.qq_id] && Object.keys(drafts[row.qq_id].changes).length,
              }"
            >
              <td>
                {{ row.qq_id
                }}<small v-if="drafts[row.qq_id]">{{ stateLabel(drafts[row.qq_id]) }}</small>
              </td>
              <td
                v-for="(label, key) in profileFields"
                :key="key"
                :class="{ 'profile-cell-dirty': dirtyField(row, key) }"
              >
                <template v-if="editing"
                  ><button
                    v-if="key === 'status'"
                    class="btn profile-status-button"
                    :disabled="['saving', 'blocked'].includes(drafts[row.qq_id]?.state)"
                    :aria-label="`${row.qq_id} 身份`"
                    @click="openDrawer(row)"
                  >
                    {{ value(row, key) || '选择身份' }}</button
                  ><input
                    v-else
                    :value="value(row, key)"
                    :aria-label="`${row.qq_id} ${label}`"
                    :aria-invalid="Boolean(drafts[row.qq_id]?.fieldErrors?.[key])"
                    :disabled="['saving', 'blocked'].includes(drafts[row.qq_id]?.state)"
                    @input="input(row, key, $event.target.value)"
                  /><small
                    v-if="drafts[row.qq_id]?.fieldErrors?.[key]"
                    class="profile-field-error"
                    >{{ drafts[row.qq_id].fieldErrors[key] }}</small
                  ></template
                ><template v-else>{{ row[key] || '—' }}</template>
              </td>
              <td>{{ permission(row) }}</td>
              <td>
                <button
                  class="btn"
                  @click="
                    flush();
                    update({ qq_id: row.qq_id });
                  "
                >
                  查看资料
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pager
        :page="data.page"
        :total="data.total"
        @change="
          (page) => {
            flush();
            update({ page });
          }
        "
      />
    </template>
    <MemberStatusDrawer
      v-if="drawerRecord"
      :member="drawerRecord.base"
      :statuses="options.statuses"
      :pending="pendingStatuses"
      :initial="drawerRecord.drawer"
      @select="selectStatus"
      @draft="rememberDrawer"
      @close="drawerQQ = null"
      @cancel="cancelDrawer"
    />
  </section>
</template>
<style scoped>
.member-profiles {
  min-width: 0;
  max-width: 100%;
}
.member-profile-heading {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}
.member-profile-heading h2 {
  margin: 0;
}
.profile-filters {
  align-items: flex-end;
  flex-wrap: wrap;
}
.profile-filters label:first-child {
  flex: 1;
  min-width: 180px;
}
.profile-filters select {
  width: 100%;
  min-width: 130px;
}
.profile-edit-bar,
.profile-notice {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  margin: 14px 0;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.profile-edit-bar {
  background: var(--hover-bg, var(--panel));
  position: sticky;
  top: 8px;
  z-index: 5;
}
.profile-edit-bar .chips {
  width: 100%;
}
.profile-table-wrap {
  max-width: 100%;
  overflow: auto;
}
.profile-table {
  min-width: 1420px;
}
.profile-table th {
  white-space: nowrap;
}
.profile-table td {
  min-width: 115px;
  max-width: 190px;
  overflow-wrap: anywhere;
}
.profile-table td:first-child {
  min-width: 100px;
}
.profile-table input {
  width: 100%;
  min-width: 110px;
  box-sizing: border-box;
}
.profile-table small {
  display: block;
  margin-top: 6px;
}
.profile-table td.profile-cell-dirty {
  box-shadow: inset 0 -2px var(--accent);
}
.profile-row-dirty {
  background: var(--hover-bg, transparent);
}
.profile-field-error {
  color: var(--danger, #b43232);
}
.profile-pending {
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 14px;
  margin: 14px 0;
}
.profile-pending .list-item {
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.profile-pending p {
  margin: 6px 0;
}
.profile-status-button {
  width: 100%;
  white-space: normal;
}
.profile-pending .chips {
  flex-wrap: wrap;
}
@media (max-width: 600px) {
  .profile-filters label {
    flex: 1 1 100%;
    min-width: 0 !important;
  }
  .member-profile-heading .btn {
    width: 100%;
  }
  .profile-edit-bar {
    position: static;
  }
  .profile-edit-bar .btn {
    flex: 1 1 auto;
  }
  .profile-notice {
    overflow-wrap: anywhere;
  }
  .profile-pending {
    padding: 10px;
  }
}
</style>
