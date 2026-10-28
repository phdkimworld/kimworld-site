package com.drkimworld.adfit;

import android.app.Notification;
import android.os.Bundle;
import android.os.Parcelable;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

/** 카카오톡 알림 중 '카카오애드핏 데일리 리포트'만 골라 서버로 보낸다. 다른 알림 내용은 읽기만 하고 저장·전송하지 않는다. */
public class NotifService extends NotificationListenerService {
    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        if (sbn == null || !"com.kakao.talk".equals(sbn.getPackageName())) return;
        Bundle ex = sbn.getNotification().extras;
        if (ex == null) return;
        String text = pick(ex);
        if (text != null) Sender.send(this, text, false, null);
    }

    static String pick(Bundle ex) {
        String[] cands = new String[] {
            str(ex.getCharSequence(Notification.EXTRA_BIG_TEXT)),
            str(ex.getCharSequence(Notification.EXTRA_TEXT))
        };
        for (String c : cands) if (c.contains(Sender.MARK)) return c;
        // 메신저형 알림(여러 메시지 묶음): 각 메시지 본문에서 찾는다
        Parcelable[] msgs = ex.getParcelableArray(Notification.EXTRA_MESSAGES);
        if (msgs != null) {
            for (int i = msgs.length - 1; i >= 0; i--) {
                if (msgs[i] instanceof Bundle) {
                    String t = str(((Bundle) msgs[i]).getCharSequence("text"));
                    if (t.contains(Sender.MARK)) return t;
                }
            }
        }
        CharSequence[] lines = ex.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
        if (lines != null) {
            StringBuilder sb = new StringBuilder();
            for (CharSequence l : lines) sb.append(str(l)).append('\n');
            if (sb.indexOf(Sender.MARK) >= 0) return sb.toString();
        }
        return null;
    }

    static String str(CharSequence c) { return c == null ? "" : c.toString(); }
}
