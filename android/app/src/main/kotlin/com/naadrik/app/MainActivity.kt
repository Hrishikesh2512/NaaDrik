package com.naadrik.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.lifecycleScope
import com.naadrik.app.demo.DemoController
import com.naadrik.app.ui.DemoScreen

class MainActivity : ComponentActivity() {
    private lateinit var controller: DemoController

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        controller = DemoController(applicationContext, lifecycleScope)
        controller.load()
        setContent {
            MaterialTheme(colorScheme = if (isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()) {
                Surface {
                    val state by controller.state.collectAsState()
                    DemoScreen(state, controller::play, controller::benchmark, controller::stop)
                }
            }
        }
    }

    override fun onStop() {
        super.onStop()
        controller.stop()
    }
}
