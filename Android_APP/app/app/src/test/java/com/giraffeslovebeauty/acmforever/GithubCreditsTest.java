package com.giraffeslovebeauty.acmforever;

import org.json.*;
import org.junit.Test;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import static org.junit.Assert.*;

public class GithubCreditsTest {
    private JSONObject source() throws Exception {
        return new JSONObject(new String(Files.readAllBytes(Paths.get("src/main/assets/" + GithubCredits.ASSET)), StandardCharsets.UTF_8));
    }
    @Test public void coversEveryBundledVersionAndPreservesActualHistory() throws Exception {
        GithubCredits credits = GithubCredits.parse(source().toString());
        JSONObject history = new JSONObject(new String(Files.readAllBytes(Paths.get("src/main/assets/" + ReleaseHistory.ASSET)), StandardCharsets.UTF_8));
        JSONArray entries = history.getJSONArray("entries");
        for (int i=0; i<entries.length(); i++) {
            String version = entries.getJSONObject(i).getString("versionName");
            assertNotNull(version, credits.versions.get(version));
            assertFalse(credits.versions.get(version).uploaders.isEmpty());
        }
        GithubCredits.Version old = credits.versions.get("0.1.0");
        assertEquals("MiaoJJ13445", old.uploaders.get(0));
        assertTrue(old.scope.contains("汇总")); assertEquals(48, old.pr);
        assertEquals("Setsuna-Yukirin", old.reviewRequesters.get(0));
        assertEquals("chatgpt-codex-connector[bot]", old.reviewers.get(0));
        assertTrue(credits.people.get(old.reviewers.get(0)).bot());
    }
    @Test public void currentSnapshotDistinguishesReviewFromPublication() throws Exception {
        JSONObject history = new JSONObject(new String(Files.readAllBytes(Paths.get("src/main/assets/" + ReleaseHistory.ASSET)), StandardCharsets.UTF_8));
        String name = history.getJSONArray("entries").getJSONObject(0).getString("versionName");
        GithubCredits.Version current = GithubCredits.parse(source().toString()).versions.get(name);
        if (current.status.equals("development")) {
            assertTrue(current.reviewers.isEmpty()); assertTrue(current.publishers.isEmpty());
        } else {
            assertTrue(current.status.equals("reviewed") || current.status.equals("published"));
            assertFalse(current.reviewers.isEmpty()); assertFalse(current.reviewRequesters.isEmpty());
            assertFalse(current.evidence.isEmpty()); assertTrue(current.pr > 0);
            if (current.status.equals("reviewed")) assertTrue(current.publishers.isEmpty());
            assertFalse(current.publication().contains("待评审"));
        }
        assertEquals("published", GithubCredits.parse(source().toString()).versions.get("0.2.21").status);
    }
    @Test public void rejectsUnknownOrRepeatedIdentityReferences() throws Exception {
        JSONObject value = source(); value.getJSONArray("thanks").put("unknown-account");
        assertThrows(JSONException.class, () -> GithubCredits.parse(value.toString()));
        JSONObject duplicate = source(); duplicate.getJSONArray("maintainers").put("MiaoJJ13445");
        assertThrows(JSONException.class, () -> GithubCredits.parse(duplicate.toString()));
    }
    @Test public void rejectsExternalProfileAndAvatarTraversal() throws Exception {
        JSONObject profile = source(); profile.getJSONArray("people").getJSONObject(0).put("profileUrl","https://github.com.evil.invalid/example");
        assertThrows(JSONException.class, () -> GithubCredits.parse(profile.toString()));
        JSONObject avatar = source(); avatar.getJSONArray("people").getJSONObject(0).put("avatar","credits/avatars/../secret.png");
        assertThrows(JSONException.class, () -> GithubCredits.parse(avatar.toString()));
    }
    @Test public void rejectsInvalidRecordAndFalsePublishedStatus() throws Exception {
        JSONObject value = source(); value.getJSONObject("versions").getJSONObject("0.2.22").put("publishers",new JSONArray());
        assertThrows(JSONException.class, () -> GithubCredits.parse(value.toString()));
        JSONObject evidence = source(); evidence.getJSONObject("versions").getJSONObject("0.2.21").put("evidence",new JSONArray().put("http://example.invalid"));
        assertThrows(JSONException.class, () -> GithubCredits.parse(evidence.toString()));
    }
    @Test public void confirmedSelfReviewsAndPublishedHistoryAreAttributedToTheirActualOwner()throws Exception{
        GithubCredits credits=GithubCredits.parse(source().toString());
        for(int minor=22;minor<=30;minor++){
            GithubCredits.Version version=credits.versions.get("0.2."+minor);
            assertEquals("published",version.status);assertEquals(java.util.Collections.singletonList("MiaoJJ13445"),version.reviewers);
            assertEquals(java.util.Collections.singletonList("MiaoJJ13445"),version.reviewRequesters);
            assertTrue(version.scope.contains("MiaoJJ13445"));assertFalse(version.evidence.isEmpty());
        }
    }
    @Test public void attributionUsesExplicitNamesInsteadOfFirstPersonNarration() throws Exception {
        GithubCredits credits = GithubCredits.parse(source().toString());
        assertFalse(credits.historyOwnerNote.contains("本人"));
        assertFalse(credits.historyOwnerNote.contains("当前候选"));
        for (GithubCredits.Person person : credits.people.values()) assertFalse(person.role.contains("本人"));
        for (GithubCredits.Version version : credits.versions.values()) assertFalse(version.scope.contains("本人"));
    }
    @Test public void reviewedSnapshotRequiresActualPeopleAndEvidenceButNotFuturePublication() throws Exception {
        JSONObject value = source();
        String name = new JSONObject(new String(Files.readAllBytes(Paths.get("src/main/assets/" + ReleaseHistory.ASSET)), StandardCharsets.UTF_8))
                .getJSONArray("entries").getJSONObject(0).getString("versionName");
        JSONObject record = value.getJSONObject("versions").getJSONObject(name);
        record.put("status", "reviewed").put("reviewRequesters", new JSONArray()).put("reviewers", new JSONArray());
        assertThrows(JSONException.class, () -> GithubCredits.parse(value.toString()));
        record.put("reviewRequesters", new JSONArray().put("MiaoJJ13445"))
                .put("reviewers", new JSONArray().put("MiaoJJ13445"))
                .put("publishers", new JSONArray()).put("pr", 999)
                .put("evidence", new JSONArray().put("https://github.com/" + GithubCredits.REPOSITORY + "/pull/999"))
                .put("scope", "Review：MiaoJJ13445（本地审查）。");
        assertEquals("构建快照已收录 Review 记录", GithubCredits.parse(value.toString()).versions.get(name).publication());
        record.put("publishers", new JSONArray().put("github-actions[bot]"));
        assertThrows(JSONException.class, () -> GithubCredits.parse(value.toString()));
        record.put("publishers", new JSONArray()).put("evidence", new JSONArray());
        assertThrows(JSONException.class, () -> GithubCredits.parse(value.toString()));
    }
    @Test public void attributionListsCannotBeChangedAfterValidation() throws Exception {
        GithubCredits credits = GithubCredits.parse(source().toString());
        assertThrows(UnsupportedOperationException.class, () -> credits.people.clear());
        assertThrows(UnsupportedOperationException.class, () -> credits.thanks.clear());
        assertThrows(UnsupportedOperationException.class, () -> credits.versions.get("0.2.21").reviewers.clear());
    }
}
