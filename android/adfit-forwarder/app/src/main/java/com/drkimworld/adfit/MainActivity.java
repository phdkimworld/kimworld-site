package com.drkimworld.adfit;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Typeface;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/** 설정 화면: 열쇠 붙여 넣기, 알림 접근 허용, 연결 시험, 마지막 알림 다시 보내기. */
public class MainActivity extends Activity {
    private TextView status, last;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        final SharedPreferences p = Sender.prefs(this);
        int pad = (int) (18 * getResources().getDisplayMetrics().density);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(pad, pad, pad, pad);

        TextView h = new TextView(this); h.setText("애드핏 전달"); h.setTextSize(24); h.setTypeface(Typeface.DEFAULT_BOLD);
        box.addView(h);
        box.addView(text("카카오톡으로 오는 '카카오애드핏' 실적 알림(데일리 리포트·매체별 보고서)만 골라 김박사 월드 운영 통계로 보냅니다. 다른 카톡 알림은 보내지 않습니다."));

        box.addView(text("\n1. 열쇠 (운영 통계 화면 → 애드핏 실적 → '열쇠 만들기'에서 복사)"));
        final EditText key = new EditText(this);
        key.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);
        key.setText(p.getString("key", ""));
        key.setHint("af_로 시작하는 열쇠");
        box.addView(key);
        box.addView(button("열쇠 저장", v -> {
            p.edit().putString("key", key.getText().toString().trim()).apply();
            Toast.makeText(this, "저장했습니다", Toast.LENGTH_SHORT).show();
        }));

        box.addView(text("\n2. 알림 읽기 허용 (목록에서 '애드핏 전달'을 켜세요)"));
        box.addView(button("알림 접근 설정 열기", v -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))));
        box.addView(text("허용이 막혀 있으면: 설정 → 애플리케이션 → 애드핏 전달 → 오른쪽 위 ⋮ → '제한된 설정 허용' 뒤 다시 시도"));

        box.addView(text("\n3. 연결 시험 (숫자는 저장되지 않습니다)"));
        box.addView(button("서버 연결 시험", v -> Sender.send(this, "연결 시험", true, (code, body) -> runOnUiThread(() -> {
            String m = code == 400 ? "연결 OK · 열쇠 맞음" : code == 401 ? "열쇠가 틀립니다" : code == 429 ? "잠시 뒤 다시" : "연결 실패 (" + code + ") " + body;
            Toast.makeText(this, m, Toast.LENGTH_LONG).show(); refresh();
        }))));
        box.addView(button("마지막 애드핏 알림 다시 보내기", v -> {
            String t = p.getString("last_text", "");
            if (!t.contains("적립금")) { Toast.makeText(this, "아직 받은 애드핏 알림이 없습니다", Toast.LENGTH_SHORT).show(); return; }
            Sender.send(this, t, true, (code, body) -> runOnUiThread(() -> { Toast.makeText(this, code == 200 ? "보냈습니다" : "실패 " + code + " " + body, Toast.LENGTH_LONG).show(); refresh(); }));
        }));

        box.addView(text("\n상태"));
        status = text(""); box.addView(status);
        last = text(""); box.addView(last);
        box.addView(text("\n배터리 최적화에서 이 앱을 '제한 없음'으로 두면 더 확실합니다."));

        ScrollView sv = new ScrollView(this); sv.addView(box);
        setContentView(sv);
    }

    @Override
    protected void onResume() { super.onResume(); refresh(); }

    private void refresh() {
        String en = Settings.Secure.getString(getContentResolver(), "enabled_notification_listeners");
        boolean on = en != null && en.contains(getPackageName());
        SharedPreferences p = Sender.prefs(this);
        status.setText((on ? "● 알림 읽기 켜짐" : "○ 알림 읽기 꺼짐 — 2번을 해 주세요") + (p.getString("key", "").isEmpty() ? "\n○ 열쇠 없음 — 1번을 해 주세요" : "\n● 열쇠 저장됨"));
        last.setText("마지막 전송: " + p.getString("last_result", "아직 없음"));
    }

    private TextView text(String s) {
        TextView t = new TextView(this); t.setText(s); t.setTextSize(15); t.setLineSpacing(0, 1.2f); return t;
    }

    private Button button(String s, android.view.View.OnClickListener l) {
        Button b = new Button(this); b.setText(s); b.setOnClickListener(l);
        b.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return b;
    }
}
