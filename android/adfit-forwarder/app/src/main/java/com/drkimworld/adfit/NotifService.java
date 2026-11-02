package com.drkimworld.adfit;

import android.app.Notification;
import android.os.Bundle;
import android.os.Parcelable;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

/** 카카오톡 알림 중 '카카오애드핏' 실적 알림(데일리 리포트·매체별 보고서)만 골라 서버로 보낸다. 다른 알림 내용은 저장·전송하지 않는다. */
public class NotifService extends NotificationListenerService {
    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null || !"com.kakao.talk".equals(sbn.getPackageName())) return;
        Bundle ex = sbn.getNotification().extras;
        if (ex == null) return;
        // 카톡은 안 읽은 메시지를 한 알림에 겹쳐 담는다(예전 리포트 + 새 리포트). 그 안의 애드핏 리포트를 모두 오래된 것부터 보낸다(1.2).
        // 서버가 날짜별로 저장하고, 같은 글은 앱이 한 번만 보낸다. 마지막(가장 새) 글이 '다시 보내기' 대상
        for (String t : picks(ex)) Sender.send(this, t, false, null);
    }

    static java.util.List<String> picks(Bundle ex) {
        java.util.List<String> out = new java.util.ArrayList<>();
        String title = str(ex.getCharSequence(Notification.EXTRA_TITLE)) + " " + str(ex.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE));
        Parcelable[] msgs = ex.getParcelableArray(Notification.EXTRA_MESSAGES);
        if (msgs != null) {
            for (Parcelable m : msgs) {
                if (m instanceof Bundle) {
                    String t = str(((Bundle) m).getCharSequence("text"));
                    String who = str(((Bundle) m).getCharSequence("sender"));
                    if (isReport(title + " " + who, t) && !out.contains(t)) out.add(t);
                }
            }
        }
        if (out.isEmpty()) { String t = pick(ex); if (t != null) out.add(t); }
        return out;
    }

    /** 애드핏 실적 글인지: 데일리 리포트 표시가 있거나, 보낸 이가 카카오애드핏이고 적립금·요청수가 들어 있음 */
    static boolean isReport(String title, String t) {
        if (t.contains(Sender.MARK)) return true;
        boolean fromAdfit = title.contains("애드핏") || t.contains("카카오애드핏") || t.contains("매체별 보고서");
        return fromAdfit && t.contains("적립금") && t.contains("요청수");
    }

    /** 잘린 미리보기 대신 가장 긴 본문을 고른다(메신저형 알림의 메시지 → 펼친 글 → 한 줄 글 순) */
    static String pick(Bundle ex) {
        String title = str(ex.getCharSequence(Notification.EXTRA_TITLE)) + " " + str(ex.getCharSequence(Notification.EXTRA_CONVERSATION_TITLE));
        String best = null;
        Parcelable[] msgs = ex.getParcelableArray(Notification.EXTRA_MESSAGES);
        if (msgs != null) {
            for (Parcelable m : msgs) {
                if (m instanceof Bundle) {
                    String t = str(((Bundle) m).getCharSequence("text"));
                    String who = str(((Bundle) m).getCharSequence("sender"));
                    if (isReport(title + " " + who, t) && (best == null || t.length() > best.length())) best = t;
                }
            }
        }
        for (String t : new String[] { str(ex.getCharSequence(Notification.EXTRA_BIG_TEXT)), str(ex.getCharSequence(Notification.EXTRA_TEXT)) }) {
            if (isReport(title, t) && (best == null || t.length() > best.length())) best = t;
        }
        CharSequence[] lines = ex.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
        if (best == null && lines != null) {
            StringBuilder sb = new StringBuilder();
            for (CharSequence l : lines) sb.append(str(l)).append('\n');
            if (isReport(title, sb.toString())) best = sb.toString();
        }
        return best;
    }

    static String str(CharSequence c) { return c == null ? "" : c.toString(); }
}
