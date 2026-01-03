package com.example.animeozvuchka;

import android.os.Bundle;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {
    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        setContentView(webView);

        webView.getSettings().setJavaScriptEnabled(true);
        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient());

        // Default URL: assumes backend serving on localhost:8000 or a configurable URL
        String url = getIntent().getStringExtra("url");
        if (url == null || url.isEmpty()) {
            url = "http://10.0.2.2:8000/"; // Android emulator localhost
        }

        webView.loadUrl(url);
    }
}
