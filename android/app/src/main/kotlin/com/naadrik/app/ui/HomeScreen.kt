package com.naadrik.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

@Composable
fun HomeScreen(
    onLive: () -> Unit,
    onDemo: () -> Unit,
) {
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text("Naadrik", style = MaterialTheme.typography.headlineLarge, modifier = Modifier.semantics { heading() })
        Text("See through sound. Use headphones.", style = MaterialTheme.typography.bodyLarge)
        Button(onClick = onLive, modifier = Modifier.fillMaxWidth().heightIn(min = 96.dp)) {
            Text("Live sensing", style = MaterialTheme.typography.headlineSmall)
        }
        OutlinedButton(onClick = onDemo, modifier = Modifier.fillMaxWidth().heightIn(min = 64.dp)) {
            Text("Sound demo and engine test", style = MaterialTheme.typography.titleMedium)
        }
    }
}
