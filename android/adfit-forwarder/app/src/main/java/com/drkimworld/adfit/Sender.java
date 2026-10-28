package com.drkimworld.adfit;

import android.content.Context;
import android.content.SharedPreferences;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** 애드핏 데일리 리포트 글을 김박사 월드 서버로 보낸다(백그라운드 스레드). 결과는 화면에 보이도록 저장한다. */
public final class Sender {
    static final String URL_BASE = "https://kimworld-api.algotraz-channel.workers.dev/v1/ingest/adfit";
    static final String MARK = "애드핏 데일리 리포트";

    public interface Done { void run(int code, String body); }

    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("adfit", Context.MODE_PRIVATE); }

    /** 같은 글은 한 번만 보낸다(force면 다시). */
    static void send(Context ctx, String text, boolean force, Done done) {
        final Context c = ctx.getApplicationContext();
        final SharedPreferences p = prefs(c);
        final String key = p.getString("key", "").trim();
        if (text == null) text = "";
        if (text.contains("적립금")) p.edit().putString("last_text", text).apply();
        final int h = text.hashCode();
        if (!force && p.getInt("last_hash", 0) == h && p.getInt("last_code", 0) == 200) return;
        final String body = text;
        new Thread(() -> {
            int code = -1; String resp;
            try {
                if (key.isEmpty()) throw new IllegalStateException("열쇠가 비어 있습니다");
                HttpURLConnection con = (HttpURLConnection) new URL(URL_BASE + "?k=" + URLEncoder.encode(key, "UTF-8")).openConnection();
                con.setConnectTimeout(15000); con.setReadTimeout(20000);
                con.setRequestMethod("POST"); con.setDoOutput(true);
                con.setRequestProperty("Content-Type", "text/plain; charset=utf-8");
                con.setRequestProperty("User-Agent", "kimworld-adfit-forwarder/1.1");
                byte[] b = body.getBytes(StandardCharsets.UTF_8);
                try (OutputStream os = con.getOutputStream()) { os.write(b); }
                code = con.getResponseCode();
                InputStream is = code >= 400 ? con.getErrorStream() : con.getInputStream();
                resp = is == null ? "" : read(is);
                con.disconnect();
            } catch (Exception e) {
                resp = e.getClass().getSimpleName() + ": " + e.getMessage();
            }
            String when = new SimpleDateFormat("MM-dd HH:mm", Locale.KOREA).format(new Date());
            SharedPreferences.Editor ed = p.edit().putString("last_result", when + " · " + code + " · " + (resp.length() > 160 ? resp.substring(0, 160) : resp)).putInt("last_code", code);
            if (code == 200) ed.putInt("last_hash", h);
            ed.apply();
            if (done != null) done.run(code, resp);
        }).start();
    }

    private static String read(InputStream is) throws Exception {
        ByteArrayOutputStream bo = new ByteArrayOutputStream(); byte[] buf = new byte[4096]; int n;
        while ((n = is.read(buf)) > 0) bo.write(buf, 0, n);
        is.close();
        return bo.toString("UTF-8");
    }

    private Sender() {}
}
