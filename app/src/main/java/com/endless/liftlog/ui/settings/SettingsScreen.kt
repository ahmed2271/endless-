package com.endless.liftlog.ui.settings

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.CloudUpload
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Restore
import androidx.compose.material.icons.rounded.TableChart
import androidx.compose.material.icons.rounded.Timer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.endless.liftlog.data.backup.BackupManager
import com.endless.liftlog.ui.components.Caption
import com.endless.liftlog.ui.components.IconCircle
import com.endless.liftlog.ui.components.LiftCard
import com.endless.liftlog.ui.theme.extended
import com.endless.liftlog.ui.workout.RestDurationStepper
import com.endless.liftlog.util.formatDay
import com.endless.liftlog.util.formatTime
import java.text.NumberFormat
import java.time.Instant

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(viewModel: SettingsViewModel, onBack: () -> Unit) {
    val status by viewModel.backupStatus.collectAsStateWithLifecycle()
    val timer by viewModel.restTimerState.collectAsStateWithLifecycle()
    val restore by viewModel.restore.collectAsStateWithLifecycle()
    val snackbar = remember { SnackbarHostState() }

    LaunchedEffect(viewModel) { viewModel.messages.collect { snackbar.showSnackbar(it) } }

    val createFile = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument(BackupManager.MIME_XLSX),
    ) { uri -> uri?.let(viewModel::backupToNewFile) }
    val openFile = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        uri?.let(viewModel::readRestoreFile)
    }
    fun chooseBackupFile() = createFile.launch("LiftLog backup.xlsx")

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            TopAppBar(
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Rounded.ArrowBack, contentDescription = "Back")
                    }
                },
                title = { Text("Settings") },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
            )
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                LiftCard {
                    CardTitle(Icons.Rounded.TableChart, MaterialTheme.extended.success, "Backup to Excel")
                    Spacer(Modifier.height(10.dp))
                    val target = status.target
                    if (target == null) {
                        Caption(
                            "Save all your workouts, sets, templates and exercises to an .xlsx file you can open " +
                                "in Excel or Google Sheets. Pick a folder like Downloads or Google Drive.",
                        )
                    } else {
                        Text(target.name, style = MaterialTheme.typography.titleSmall)
                        Caption(
                            status.lastBackupAt?.let { "Last backup ${formatDay(Instant.ofEpochMilli(it))}, ${formatTime(Instant.ofEpochMilli(it))}" }
                                ?: "Not backed up yet",
                        )
                    }
                    status.lastError?.let {
                        Spacer(Modifier.height(6.dp))
                        Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    }
                    Spacer(Modifier.height(14.dp))
                    Button(
                        onClick = { viewModel.backupNow(::chooseBackupFile) },
                        enabled = !status.inProgress,
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                        shape = MaterialTheme.shapes.medium,
                    ) {
                        if (status.inProgress) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(20.dp),
                                strokeWidth = 2.dp,
                                color = MaterialTheme.colorScheme.onPrimary,
                            )
                        } else {
                            Icon(Icons.Rounded.CloudUpload, contentDescription = null)
                        }
                        Spacer(Modifier.width(10.dp))
                        Text(if (target == null) "Back up to Excel" else "Update backup")
                    }
                    if (target != null) {
                        TextButton(onClick = ::chooseBackupFile, modifier = Modifier.fillMaxWidth()) {
                            Text("Save to a different file")
                        }
                        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { viewModel.setAutoBackup(!status.autoBackup) }
                                .heightIn(min = 56.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text("Update after every workout", style = MaterialTheme.typography.bodyLarge)
                                Caption("Keeps this file up to date automatically")
                            }
                            Switch(checked = status.autoBackup, onCheckedChange = viewModel::setAutoBackup)
                        }
                    }
                }
            }

            item {
                LiftCard {
                    CardTitle(Icons.Rounded.Restore, MaterialTheme.colorScheme.primary, "Restore from Excel")
                    Spacer(Modifier.height(10.dp))
                    Caption(
                        "Replaces the data in LiftLog with a backup file. You can edit the file in Excel first " +
                            "— fix a weight, add sets or rename a template — and restore it.",
                    )
                    Spacer(Modifier.height(14.dp))
                    OutlinedButton(
                        onClick = {
                            openFile.launch(
                                arrayOf(BackupManager.MIME_XLSX, "application/vnd.ms-excel", "application/octet-stream"),
                            )
                        },
                        enabled = restore == RestoreState.Idle,
                        modifier = Modifier.fillMaxWidth().height(52.dp),
                        shape = MaterialTheme.shapes.medium,
                    ) { Text("Choose backup file") }
                }
            }

            item {
                LiftCard {
                    CardTitle(Icons.Rounded.Timer, MaterialTheme.colorScheme.tertiary, "Rest timer")
                    Spacer(Modifier.height(4.dp))
                    Caption("Starts automatically after each set you tick off.")
                    Spacer(Modifier.height(12.dp))
                    RestDurationStepper(
                        seconds = timer.defaultSeconds,
                        onChange = viewModel::setDefaultRest,
                        modifier = Modifier.align(Alignment.CenterHorizontally),
                    )
                }
            }

            item {
                LiftCard {
                    CardTitle(Icons.Rounded.Info, MaterialTheme.colorScheme.secondary, "About")
                    Spacer(Modifier.height(8.dp))
                    Caption(
                        "LiftLog keeps everything on this phone: no account and no internet access. " +
                            "Backups go only where you choose to save them.",
                    )
                }
            }
        }
    }

    when (val r = restore) {
        is RestoreState.Preview -> {
            val data = r.backup.data
            val n = NumberFormat.getIntegerInstance()
            AlertDialog(
                onDismissRequest = viewModel::cancelRestore,
                title = { Text("Restore this backup?") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        r.fileName?.let { Text(it, style = MaterialTheme.typography.titleSmall) }
                        Text(
                            "${n.format(data.workouts.size)} workouts, ${n.format(data.sets.size)} sets, " +
                                "${n.format(data.templates.size)} templates, ${n.format(data.exercises.size)} exercises.",
                            style = MaterialTheme.typography.bodyLarge,
                        )
                        Text(
                            "Everything currently in LiftLog will be replaced.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.error,
                        )
                        if (r.backup.skippedRows > 0) {
                            Caption("${r.backup.skippedRows} rows will be skipped:")
                            r.backup.warnings.take(3).forEach { Caption("• $it") }
                        }
                    }
                },
                confirmButton = {
                    TextButton(onClick = viewModel::confirmRestore) {
                        Text("Replace and restore", color = MaterialTheme.colorScheme.error)
                    }
                },
                dismissButton = { TextButton(onClick = viewModel::cancelRestore) { Text("Cancel") } },
                containerColor = MaterialTheme.extended.card,
            )
        }
        RestoreState.Reading, RestoreState.Restoring -> {
            AlertDialog(
                onDismissRequest = {},
                title = { Text(if (r == RestoreState.Reading) "Reading backup…" else "Restoring…") },
                text = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(modifier = Modifier.size(28.dp))
                        Spacer(Modifier.width(16.dp))
                        Caption("This only takes a moment.")
                    }
                },
                confirmButton = {},
                containerColor = MaterialTheme.extended.card,
            )
        }
        RestoreState.Idle -> Unit
    }
}

@Composable
private fun CardTitle(icon: ImageVector, tint: androidx.compose.ui.graphics.Color, title: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        IconCircle(icon, tint)
        Spacer(Modifier.width(12.dp))
        Text(title, style = MaterialTheme.typography.titleMedium)
    }
}
