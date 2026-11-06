package com.giraffeslovebeauty.acmforever;

import android.content.Context;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** A bundled, dated attribution snapshot. No credentials or live GitHub calls. */
final class GithubCredits {
    static final String ASSET = "releases/credits.json";
    static final String REPOSITORY = "GiraffesLoveBeauty/ACM-Forever";
    final String capturedOn, historyOwnerNote;
    final Map<String, Person> people;
    final List<String> thanks, maintainers;
    final Map<String, Version> versions;

    private GithubCredits(JSONObject root) throws JSONException {
        if (root.getInt("schemaVersion") != 1 || !REPOSITORY.equals(root.getString("repository")))
            throw new JSONException("人员记录格式无效");
        capturedOn = required(root, "capturedOn", 10);
        if (!capturedOn.matches("[0-9]{4}-[0-9]{2}-[0-9]{2}")) throw new JSONException("人员记录日期无效");
        historyOwnerNote = required(root, "historyOwnerNote", 500);
        JSONArray entries = root.getJSONArray("people");
        if (entries.length() < 1 || entries.length() > 200) throw new JSONException("参与者数量无效");
        LinkedHashMap<String, Person> persons = new LinkedHashMap<>();
        for (int i = 0; i < entries.length(); i++) {
            Person person = new Person(entries.getJSONObject(i));
            if (persons.put(person.login, person) != null) throw new JSONException("参与者重复");
        }
        people = Collections.unmodifiableMap(persons);
        thanks = references(root.getJSONArray("thanks"));
        maintainers = references(root.getJSONArray("maintainers"));
        JSONObject releases = root.getJSONObject("versions");
        if (releases.length() < 1 || releases.length() > 200) throw new JSONException("版本人员记录数量无效");
        LinkedHashMap<String, Version> out = new LinkedHashMap<>();
        Iterator<String> names = releases.keys();
        while (names.hasNext()) {
            String name = names.next();
            if (!name.matches("[0-9]{1,6}\\.[0-9]{1,6}\\.[0-9]{1,6}")) throw new JSONException("人员记录版本无效");
            out.put(name, new Version(releases.getJSONObject(name)));
        }
        versions = Collections.unmodifiableMap(out);
    }

    static GithubCredits parse(String text) throws JSONException { return new GithubCredits(new JSONObject(text)); }

    static GithubCredits load(Context context) throws IOException, JSONException {
        try (InputStream in = context.getAssets().open(ASSET); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4096]; int n;
            while ((n = in.read(buffer)) != -1) {
                if (out.size() + n > 262144) throw new IOException("人员记录过大");
                out.write(buffer, 0, n);
            }
            return parse(new String(out.toByteArray(), StandardCharsets.UTF_8));
        }
    }

    private List<String> references(JSONArray array) throws JSONException {
        if (array.length() > 200) throw new JSONException("人员引用过多");
        ArrayList<String> out = new ArrayList<>();
        for (int i = 0; i < array.length(); i++) {
            String login = array.getString(i);
            if (!people.containsKey(login) || out.contains(login)) throw new JSONException("人员引用无效");
            out.add(login);
        }
        return Collections.unmodifiableList(out);
    }

    private static String required(JSONObject object, String key, int limit) throws JSONException {
        String value = object.getString(key).trim();
        if (value.isEmpty() || value.length() > limit) throw new JSONException("人员记录内容无效");
        return value;
    }

    static final class Person {
        final String login, kind, profileUrl, avatar, role;
        Person(JSONObject value) throws JSONException {
            login = required(value, "login", 50); kind = required(value, "kind", 4);
            profileUrl = required(value, "profileUrl", 180); avatar = required(value, "avatar", 80);
            role = required(value, "role", 150);
            if (!login.matches("[A-Za-z0-9][A-Za-z0-9-]{0,38}(?:\\[bot\\])?")
                    || !(kind.equals("user") || kind.equals("bot"))
                    || !profileUrl.matches("https://github\\.com/(?:[A-Za-z0-9-]+|apps/[A-Za-z0-9-]+)")
                    || !avatar.matches("credits/avatars/[0-9]+\\.png")) throw new JSONException("GitHub身份或头像路径无效");
        }
        boolean bot() { return kind.equals("bot"); }
    }

    final class Version {
        final List<String> uploaders, reviewRequesters, reviewers, publishers, evidence;
        final String status, scope;
        final int pr;
        Version(JSONObject value) throws JSONException {
            uploaders = references(value.getJSONArray("uploaders"));
            reviewRequesters = references(value.getJSONArray("reviewRequesters"));
            reviewers = references(value.getJSONArray("reviewers"));
            publishers = references(value.getJSONArray("publishers"));
            status = required(value, "status", 20); scope = required(value, "scope", 500); pr = value.getInt("pr");
            if (uploaders.isEmpty() || pr < 0 || !Arrays.asList("development", "published", "unpublished").contains(status))
                throw new JSONException("版本署名信息无效");
            if (status.equals("published") && publishers.isEmpty()) throw new JSONException("公开版本缺少发布记录");
            JSONArray urls = value.getJSONArray("evidence");
            if (urls.length() > 20) throw new JSONException("人员来源记录过多");
            ArrayList<String> sources = new ArrayList<>();
            for (int i = 0; i < urls.length(); i++) {
                String url = urls.getString(i);
                if (pr == 0 || !url.matches("https://github\\.com/" + REPOSITORY + "/pull/" + pr + "(?:#[A-Za-z0-9-]+)?"))
                    throw new JSONException("人员来源链接无效");
                sources.add(url);
            }
            evidence = Collections.unmodifiableList(sources);
        }
        String publication() {
            if (status.equals("published")) return "已有公开发布记录";
            if (status.equals("development")) return "当前开发版本 · 待评审与发布";
            return "未收录公开 APK 发布记录";
        }
    }
}
