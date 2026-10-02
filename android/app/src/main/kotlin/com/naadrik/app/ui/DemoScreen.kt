package com.naadrik.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.naadrik.app.demo.DemoState
import com.naadrik.core.sound.SCENARIOS
import com.naadrik.core.sound.Scenario

private val TOUCH_TARGET = 64.dp

@Composable
fun DemoScreen(
    state: DemoState,
    onPlay: (Scenario) -> Unit,
    onBenchmark: () -> Unit,
    onStop: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Naadrik sound demo", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.semantics { heading() })
                Text("Use headphones. Left and right matter.", style = MaterialTheme.typography.bodyLarge)
                Text(
                    state.status,
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                )
            }
        }
        item {
            Button(
                onClick = onBenchmark,
                enabled = state.ready && !state.busy,
                modifier = Modifier.fillMaxWidth().heightIn(min = TOUCH_TARGET),
            ) { Text("Engine test (10 seconds)", style = MaterialTheme.typography.titleMedium) }
        }
        item {
            OutlinedButton(
                onClick = onStop,
                enabled = state.busy,
                modifier = Modifier.fillMaxWidth().heightIn(min = TOUCH_TARGET),
            ) { Text("Stop", style = MaterialTheme.typography.titleMedium) }
        }
        items(SCENARIOS) { scenario ->
            OutlinedButton(
                onClick = { onPlay(scenario) },
                enabled = state.ready && !state.busy,
                modifier =
                    Modifier
                        .fillMaxWidth()
                        .heightIn(min = TOUCH_TARGET)
                        .semantics { contentDescription = "Play ${scenario.name}. ${scenario.description}" },
            ) {
                Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Text(scenario.name, style = MaterialTheme.typography.titleMedium)
                    Text(scenario.description, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
        if (state.report.isNotEmpty()) {
            item { Text("Report", style = MaterialTheme.typography.titleLarge, modifier = Modifier.semantics { heading() }) }
            items(state.report) { line -> Text(line, style = MaterialTheme.typography.bodySmall) }
        }
    }
}
