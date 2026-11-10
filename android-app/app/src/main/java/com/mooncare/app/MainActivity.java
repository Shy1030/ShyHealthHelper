package com.mooncare.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.view.View;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;
import android.widget.Toast;

import androidx.core.content.FileProvider;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.List;

public class MainActivity extends Activity {

    private static final int REQUEST_FILE = 4101;
    private static final String LOCAL_BASE = "http://127.0.0.1:8000";
    // 标记为内置版：前端据此跳过 Service Worker，避免更新后继续使用旧页面缓存
    private static final String LOCAL_URL = LOCAL_BASE + "/?embedded=1";
    private static final String APP_PREFS = "mooncare_app";
    private static final String KEY_LAST_VERSION = "last_version_code";

    private WebView webView;
    private ValueCallback<Uri[]> filePathCallback;
    private Uri cameraPhotoUri;
    private boolean serverReady = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        configureSystemBars();
        clearWebViewCacheOnUpgrade();
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webView);
        applyResponsiveInsets();
        configureWebView();

        TextView reload = findViewById(R.id.btnReload);
        reload.setOnClickListener(v -> {
            if (serverReady) {
                webView.loadUrl(LOCAL_URL);
            } else {
                startPythonBackend();
            }
        });

        if (savedInstanceState != null) {
            webView.restoreState(savedInstanceState);
        } else {
            startPythonBackend();
        }
    }

    private void configureSystemBars() {
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        getWindow().setStatusBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            getWindow().setNavigationBarColor(Color.TRANSPARENT);
        } else {
            getWindow().setNavigationBarColor(Color.parseColor("#6D4557"));
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            getWindow().setStatusBarContrastEnforced(false);
            getWindow().setNavigationBarContrastEnforced(false);
        }

        WindowInsetsControllerCompat controller =
                WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        controller.setAppearanceLightStatusBars(false);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            controller.setAppearanceLightNavigationBars(true);
        }
    }

    /**
     * 顶部栏避开状态栏/刘海，WebView 避开侧边刘海和底部导航栏/输入法。
     * 横竖屏切换时由 onConfigurationChanged 重新应用。
     */
    private void applyResponsiveInsets() {
        View root = findViewById(R.id.rootLayout);
        View topBar = findViewById(R.id.topBar);
        View web = findViewById(R.id.webView);
        if (root == null || topBar == null || web == null) {
            return;
        }
        final int baseStart = dp(14);
        final int baseEnd = dp(6);
        ViewCompat.setOnApplyWindowInsetsListener(root, (view, insets) -> {
            Insets bars = insets.getInsets(
                    WindowInsetsCompat.Type.systemBars()
                            | WindowInsetsCompat.Type.displayCutout()
            );
            Insets ime = insets.getInsets(WindowInsetsCompat.Type.ime());
            topBar.setPadding(
                    baseStart + bars.left,
                    bars.top,
                    baseEnd + bars.right,
                    0
            );
            web.setPadding(
                    bars.left,
                    0,
                    bars.right,
                    Math.max(bars.bottom, ime.bottom)
            );
            return insets;
        });
        ViewCompat.requestApplyInsets(root);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        View root = findViewById(R.id.rootLayout);
        if (root != null) {
            ViewCompat.requestApplyInsets(root);
        }
    }

    private void startPythonBackend() {
        final File dataDir = new File(getFilesDir(), "mooncare_data");
        final File webDir = new File(getFilesDir(), "web");
        try {
            copyAssetDir("web", webDir);
        } catch (IOException exception) {
            showError("解压前端资源失败：" + exception.getMessage());
            return;
        }

        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }

        new Thread(() -> {
            try {
                Python.getInstance()
                        .getModule("server")
                        .callAttr(
                                "start",
                                dataDir.getAbsolutePath(),
                                webDir.getAbsolutePath(),
                                "127.0.0.1",
                                8000
                        );
            } catch (Throwable throwable) {
                runOnUiThread(() -> showError("Python 后端启动失败：\n" + throwable));
                return;
            }

            boolean ready = waitForServer();
            runOnUiThread(() -> {
                if (ready) {
                    serverReady = true;
                    webView.loadUrl(LOCAL_URL);
                } else {
                    showError("后端已启动，但健康检查失败。请查看 Logcat 中的 python.stderr。");
                }
            });
        }).start();
    }

    /**
     * 版本升级时只清理 WebView 缓存与前端静态资源，保留 files/mooncare_data 里的数据库、
     * 上传图片、AI Key 和小米凭证。这样新 APK 的页面和 Python 代码会立即生效，不会出现
     * “安装成功但打开还是旧功能”的问题。
     */
    private void clearWebViewCacheOnUpgrade() {
        SharedPreferences prefs = getSharedPreferences(APP_PREFS, MODE_PRIVATE);
        int lastVersion = prefs.getInt(KEY_LAST_VERSION, 0);
        if (lastVersion == BuildConfig.VERSION_CODE) {
            return;
        }

        File appRoot = getFilesDir().getParentFile();
        if (appRoot != null) {
            File[] webViewDirs = appRoot.listFiles(
                    (dir, name) -> name.startsWith("app_webview")
            );
            if (webViewDirs != null) {
                for (File webViewDir : webViewDirs) {
                    deleteRecursive(webViewDir);
                }
            }
        }
        // 强制重新解压最新前端资源；不会删除同级的 mooncare_data
        deleteRecursive(new File(getFilesDir(), "web"));

        prefs.edit().putInt(KEY_LAST_VERSION, BuildConfig.VERSION_CODE).apply();
    }

    private void deleteRecursive(File file) {
        if (file == null || !file.exists()) {
            return;
        }
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children != null) {
                for (File child : children) {
                    deleteRecursive(child);
                }
            }
        }
        //noinspection ResultOfMethodCallIgnored
        file.delete();
    }

    private boolean waitForServer() {
        for (int attempt = 0; attempt < 60; attempt++) {
            try {
                HttpURLConnection connection =
                        (HttpURLConnection) new URL(LOCAL_BASE + "/api/health").openConnection();
                connection.setConnectTimeout(1000);
                connection.setReadTimeout(1000);
                int code = connection.getResponseCode();
                connection.disconnect();
                if (code == 200) {
                    return true;
                }
            } catch (IOException ignored) {
                // 继续等待
            }
            try {
                Thread.sleep(500);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return false;
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        // 本地静态资源不需要 HTTP 缓存，避免升级后继续使用旧页面
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
                if (scheme.equals("http") || scheme.equals("https")) {
                    if ("127.0.0.1".equals(uri.getHost()) || "localhost".equals(uri.getHost())) {
                        return false;
                    }
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (Exception ignored) {
                }
                return true;
            }

            @Override
            public void onReceivedError(
                    WebView view,
                    WebResourceRequest request,
                    WebResourceError error
            ) {
                if (request.isForMainFrame()) {
                    runOnUiThread(() -> Toast.makeText(
                            MainActivity.this,
                            "页面加载失败：" + error.getDescription(),
                            Toast.LENGTH_LONG
                    ).show());
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(
                    WebView view,
                    ValueCallback<Uri[]> callback,
                    FileChooserParams params
            ) {
                if (filePathCallback != null) {
                    filePathCallback.onReceiveValue(null);
                }
                filePathCallback = callback;
                cameraPhotoUri = null;

                Intent galleryIntent = new Intent(Intent.ACTION_GET_CONTENT);
                galleryIntent.addCategory(Intent.CATEGORY_OPENABLE);
                galleryIntent.setType("image/*");

                Intent chooser;
                try {
                    File imagesDir = new File(getCacheDir(), "images");
                    if (!imagesDir.exists() && !imagesDir.mkdirs()) {
                        throw new IllegalStateException("无法创建相机目录");
                    }
                    File photoFile = File.createTempFile("camera_", ".jpg", imagesDir);
                    cameraPhotoUri = FileProvider.getUriForFile(
                            MainActivity.this,
                            getPackageName() + ".fileprovider",
                            photoFile
                    );
                    Intent captureIntent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                    captureIntent.putExtra(MediaStore.EXTRA_OUTPUT, cameraPhotoUri);
                    captureIntent.addFlags(
                            Intent.FLAG_GRANT_READ_URI_PERMISSION
                                    | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                    );
                    List<ResolveInfo> cameraApps = getPackageManager()
                            .queryIntentActivities(captureIntent, PackageManager.MATCH_DEFAULT_ONLY);
                    for (ResolveInfo info : cameraApps) {
                        grantUriPermission(
                                info.activityInfo.packageName,
                                cameraPhotoUri,
                                Intent.FLAG_GRANT_READ_URI_PERMISSION
                                        | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                        );
                    }
                    chooser = Intent.createChooser(galleryIntent, "拍照或选择图片");
                    chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{captureIntent});
                    chooser.addFlags(
                            Intent.FLAG_GRANT_READ_URI_PERMISSION
                                    | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                    );
                } catch (Exception exception) {
                    cameraPhotoUri = null;
                    chooser = Intent.createChooser(galleryIntent, "选择图片");
                }

                try {
                    startActivityForResult(chooser, REQUEST_FILE);
                    return true;
                } catch (Exception exception) {
                    filePathCallback = null;
                    Toast.makeText(MainActivity.this, "没有可用的图片选择器", Toast.LENGTH_LONG).show();
                    return false;
                }
            }
        });
    }

    private void copyAssetDir(String assetPath, File targetDir) throws IOException {
        String[] children = getAssets().list(assetPath);
        if (children == null || children.length == 0) {
            if (!targetDir.getParentFile().exists() && !targetDir.getParentFile().mkdirs()) {
                throw new IOException("无法创建目录：" + targetDir.getParentFile());
            }
            try (InputStream input = getAssets().open(assetPath);
                 OutputStream output = new FileOutputStream(targetDir)) {
                byte[] buffer = new byte[8192];
                int length;
                while ((length = input.read(buffer)) > 0) {
                    output.write(buffer, 0, length);
                }
            }
            return;
        }
        if (!targetDir.exists() && !targetDir.mkdirs()) {
            throw new IOException("无法创建目录：" + targetDir);
        }
        for (String child : children) {
            copyAssetDir(assetPath + "/" + child, new File(targetDir, child));
        }
    }

    private void showError(String message) {
        new AlertDialog.Builder(this)
                .setTitle("ShyHealthHelper 启动失败")
                .setMessage(message)
                .setPositiveButton("重试", (dialog, which) -> startPythonBackend())
                .setNegativeButton("关闭", (dialog, which) -> finish())
                .show();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_FILE) return;
        Uri[] results = null;
        if (resultCode == RESULT_OK) {
            if (data != null && data.getClipData() != null) {
                int count = data.getClipData().getItemCount();
                results = new Uri[count];
                for (int i = 0; i < count; i++) {
                    results[i] = data.getClipData().getItemAt(i).getUri();
                }
            } else if (data != null && data.getData() != null) {
                results = new Uri[]{data.getData()};
            } else if (cameraPhotoUri != null) {
                try {
                    if (getContentResolver().openInputStream(cameraPhotoUri) != null) {
                        results = new Uri[]{cameraPhotoUri};
                    }
                } catch (Exception ignored) {
                    results = null;
                }
            }
        }
        if (filePathCallback != null) {
            filePathCallback.onReceiveValue(results);
            filePathCallback = null;
        }
        cameraPhotoUri = null;
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (webView != null) {
            webView.saveState(outState);
        }
    }

    @Override
    protected void onPause() {
        if (webView != null) webView.onPause();
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) webView.onResume();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.loadUrl("about:blank");
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
