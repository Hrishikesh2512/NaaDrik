package com.naadrik.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.view.PreviewView
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.naadrik.app.demo.DemoController
import com.naadrik.app.live.LiveController
import com.naadrik.app.ui.DemoScreen
import com.naadrik.app.ui.HomeScreen
import com.naadrik.app.ui.LiveScreen

private enum class Screen { Home, Live, Demo }

class MainActivity : ComponentActivity() {
    private lateinit var demo: DemoController
    private lateinit var live: LiveController

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        demo = DemoController(applicationContext, lifecycleScope)
        demo.load()
        live = LiveController(applicationContext, lifecycleScope)
        val previewView = PreviewView(this).apply { scaleType = PreviewView.ScaleType.FIT_CENTER }
        setContent {
            MaterialTheme(colorScheme = if (isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()) {
                Surface {
                    var screen by rememberSaveable { mutableStateOf(Screen.Home) }
                    var cameraDenied by remember { mutableStateOf(false) }
                    val askCamera =
                        rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
                            cameraDenied = !granted
                            if (granted) live.start(this, previewView.surfaceProvider)
                        }
                    BackHandler(enabled = screen != Screen.Home) {
                        live.stop()
                        demo.stop()
                        screen = Screen.Home
                    }
                    when (screen) {
                        Screen.Home -> HomeScreen(onLive = { screen = Screen.Live }, onDemo = { screen = Screen.Demo })
                        Screen.Demo -> {
                            val state by demo.state.collectAsState()
                            DemoScreen(state, demo::play, demo::benchmark, demo::stop)
                        }
                        Screen.Live -> {
                            val state by live.state.collectAsState()
                            val frequencies by produceState<DoubleArray?>(null) {
                                value =
                                    EngineProvider.get(applicationContext).bank.frequencies
                            }
                            LiveScreen(
                                state = if (cameraDenied) state.copy(status = "Camera permission is needed for live sensing.") else state,
                                previewView = previewView,
                                frequencies = frequencies,
                                onStart = {
                                    if (hasCamera()) {
                                        live.start(
                                            this,
                                            previewView.surfaceProvider,
                                        )
                                    } else {
                                        askCamera.launch(Manifest.permission.CAMERA)
                                    }
                                },
                                onStop = live::stop,
                            )
                        }
                    }
                }
            }
        }
    }

    private fun hasCamera() = ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    override fun onStop() {
        super.onStop()
        demo.stop()
        live.stop()
    }
}
