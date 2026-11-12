package com.endless.liftlog.ui.settings

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.endless.liftlog.data.backup.BackupManager
import com.endless.liftlog.data.backup.BackupStatus
import com.endless.liftlog.data.backup.ParsedBackup
import com.endless.liftlog.data.repository.WorkoutRepository
import com.endless.liftlog.timer.RestTimer
import com.endless.liftlog.timer.RestTimerState
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.text.NumberFormat

sealed interface RestoreState {
    data object Idle : RestoreState
    data object Reading : RestoreState
    data class Preview(val backup: ParsedBackup, val fileName: String?) : RestoreState
    data object Restoring : RestoreState
}

class SettingsViewModel(
    private val backup: BackupManager,
    workouts: WorkoutRepository,
    private val restTimer: RestTimer,
) : ViewModel() {

    val backupStatus: StateFlow<BackupStatus> = backup.status
    val restTimerState: StateFlow<RestTimerState> = restTimer.state
    val hasActiveWorkout: StateFlow<Boolean> = workouts.activeSession.map { it != null }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), false)

    private val _restore = MutableStateFlow<RestoreState>(RestoreState.Idle)
    val restore: StateFlow<RestoreState> = _restore.asStateFlow()

    private val messageChannel = Channel<String>(Channel.BUFFERED)
    val messages: Flow<String> = messageChannel.receiveAsFlow()

    /** "Back up now": updates the remembered file, or asks for one via [chooseFile]. */
    fun backupNow(chooseFile: () -> Unit) {
        if (backup.status.value.target == null) {
            chooseFile()
            return
        }
        viewModelScope.launch {
            backup.updateBackup()
                .onSuccess { message("Backup updated") }
                .onFailure { message(it.message ?: "Backup failed") }
        }
    }

    fun backupToNewFile(uri: Uri) {
        viewModelScope.launch {
            backup.backupToNewFile(uri)
                .onSuccess { message("Backup saved") }
                .onFailure { message(it.message ?: "Backup failed") }
        }
    }

    fun setAutoBackup(enabled: Boolean) = backup.setAutoBackup(enabled)

    fun forgetBackupFile() = backup.forgetTarget()

    fun readRestoreFile(uri: Uri) {
        if (hasActiveWorkout.value) {
            message("Finish or discard the workout in progress before restoring")
            return
        }
        _restore.value = RestoreState.Reading
        viewModelScope.launch {
            backup.readBackup(uri)
                .onSuccess { _restore.value = RestoreState.Preview(it, backup.fileName(uri)) }
                .onFailure {
                    _restore.value = RestoreState.Idle
                    message(it.message ?: "Couldn't read that file")
                }
        }
    }

    fun confirmRestore() {
        val preview = _restore.value as? RestoreState.Preview ?: return
        _restore.value = RestoreState.Restoring
        viewModelScope.launch {
            backup.restore(preview.backup.data)
                .onSuccess {
                    val n = NumberFormat.getIntegerInstance()
                    message("Restored ${n.format(it.workouts)} workouts and ${n.format(it.sets)} sets")
                }
                .onFailure { message("Restore failed: ${it.message ?: "unknown error"}. Nothing was changed.") }
            _restore.value = RestoreState.Idle
        }
    }

    fun cancelRestore() {
        _restore.value = RestoreState.Idle
    }

    fun setDefaultRest(seconds: Int) = restTimer.setDefault(seconds)

    private fun message(text: String) {
        viewModelScope.launch { messageChannel.send(text) }
    }
}
