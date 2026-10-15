package com.daedalustcg.jfinances.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.UnfoldMore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.daedalustcg.jfinances.app.LocalAppModel
import com.daedalustcg.jfinances.kit.api.ApiError
import com.daedalustcg.jfinances.kit.ui.JF
import com.daedalustcg.jfinances.kit.ui.JFFont
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

// The phone's forms, in the design system's dress: a sheet with Cancel and
// Save, fields with a mono caption over them, choices as menus or chips. Every
// edit on the phone goes through one of these, as the web's go through
// @mooney/ui's Drawer and Input, and as the iPhone app's go through Forms.swift.

/**
 * A sheet that edits something: a title, Cancel, Save (disabled until the form
 * is valid; a spinner while it saves), the error if saving failed. `save`
 * throws to keep the sheet open; returning dismisses it and reloads every
 * screen (the model's refresh token), so lists show the change.
 */
@Composable
fun FormSheet(
    title: String,
    onDismiss: () -> Unit,
    saveLabel: String = "Save",
    canSave: Boolean = true,
    destructive: Boolean = false,
    save: suspend () -> Unit,
    content: @Composable ColumnScope.() -> Unit,
) {
    val model = LocalAppModel.current
    val scope = rememberCoroutineScope()
    var saving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    Dialog(
        onDismissRequest = { if (!saving) onDismiss() },
        properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false),
    ) {
        Column(
            Modifier
                .fillMaxSize()
                .background(JF.page)
                .statusBarsPadding()
                .navigationBarsPadding()
                .imePadding(),
        ) {
            Row(
                Modifier.fillMaxWidth().height(52.dp).padding(horizontal = JF.gutter),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(onClick = onDismiss, enabled = !saving) {
                    Text("Cancel", style = JFFont.sans(16f), color = JF.accentText)
                }
                Text(
                    title,
                    style = JFFont.sans(17f, JFFont.Weight.Semibold),
                    color = JF.ink,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.weight(1f),
                )
                TextButton(
                    onClick = {
                        scope.launch {
                            saving = true
                            error = null
                            try {
                                save()
                                model.changed()
                                onDismiss()
                            } catch (e: CancellationException) {
                                throw e
                            } catch (e: ApiError) {
                                model.handle(e)
                                error = e.description
                            } catch (e: Exception) {
                                error = e.message ?: "Something went wrong."
                            } finally {
                                saving = false
                            }
                        }
                    },
                    enabled = canSave && !saving,
                ) {
                    if (saving) {
                        CircularProgressIndicator(Modifier.size(18.dp), color = JF.ink3, strokeWidth = 2.dp)
                    } else {
                        Text(
                            saveLabel,
                            style = JFFont.sans(16f, JFFont.Weight.Semibold),
                            color = if (!canSave) JF.ink3 else if (destructive) JF.neg else JF.accentText,
                        )
                    }
                }
            }
            Column(
                Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = JF.gutter, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                error?.let { ErrorNote(it) }
                content()
            }
        }
    }
}

/** A caption and a text field, with help under it, or what is wrong with it. */
@Composable
fun Field(
    label: String,
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String = "",
    mono: Boolean = false,
    keyboard: KeyboardType = KeyboardType.Text,
    capitalization: KeyboardCapitalization = KeyboardCapitalization.Sentences,
    help: String? = null,
    error: String? = null,
    uppercase: Boolean = false,
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = JFFont.mono(11f), color = JF.ink3)
        Box(
            Modifier
                .fillMaxWidth()
                .height(42.dp)
                .background(JF.panel2)
                .border(1.dp, if (error == null) JF.line else JF.neg, RectangleShape)
                .padding(horizontal = 12.dp),
            contentAlignment = Alignment.CenterStart,
        ) {
            if (value.isEmpty()) Text(placeholder, style = if (mono) JFFont.mono(15f) else JFFont.sans(15f), color = JF.ink3, maxLines = 1)
            BasicTextField(
                value = value,
                onValueChange = { onChange(if (uppercase) it.uppercase() else it) },
                singleLine = true,
                textStyle = (if (mono) JFFont.mono(15f) else JFFont.sans(15f)).copy(color = JF.ink),
                cursorBrush = SolidColor(JF.accent),
                keyboardOptions = KeyboardOptions(
                    keyboardType = keyboard,
                    capitalization = if (uppercase) KeyboardCapitalization.Characters else capitalization,
                    autoCorrectEnabled = !(mono || uppercase),
                ),
                modifier = Modifier.fillMaxWidth(),
            )
        }
        when {
            error != null -> Text(error, style = JFFont.mono(11f), color = JF.neg)
            !help.isNullOrEmpty() -> Text(help, style = JFFont.mono(11f), color = JF.ink3)
        }
    }
}

/** A caption over a row of chips, the small segmented choice. */
@Composable
fun <V> ChoiceField(label: String, options: List<Pair<V, String>>, value: V, onChange: (V) -> Unit, help: String? = null) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = JFFont.mono(11f), color = JF.ink3)
        Row(Modifier.horizontalScroll(rememberScrollState())) { Chips(options, value, onChange) }
        if (!help.isNullOrEmpty()) Text(help, style = JFFont.mono(11f), color = JF.ink3)
    }
}

/** One choice in a [MenuField]; `header` opens a section before it. */
data class MenuItem(val label: String, val onPick: () -> Unit, val header: String? = null)

/** A caption over a menu button, for a long list of choices (categories, groups). */
@Composable
fun MenuField(label: String, current: String, options: List<MenuItem>, help: String? = null) {
    var open by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = JFFont.mono(11f), color = JF.ink3)
        Box {
            Row(
                Modifier
                    .fillMaxWidth()
                    .height(42.dp)
                    .background(JF.panel2)
                    .border(1.dp, JF.line, RectangleShape)
                    .clickable(role = Role.DropdownList) { open = true }
                    .padding(horizontal = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(current, style = JFFont.sans(15f), color = JF.ink, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                Icon(Icons.Filled.UnfoldMore, contentDescription = null, tint = JF.ink3, modifier = Modifier.size(16.dp))
            }
            DropdownMenu(
                expanded = open,
                onDismissRequest = { open = false },
                containerColor = JF.panel,
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.heightIn(max = 420.dp),
            ) {
                options.forEach { item ->
                    item.header?.let { h ->
                        Text(h, style = JFFont.mono(11f), color = JF.ink3, modifier = Modifier.padding(start = 12.dp, top = 10.dp, bottom = 2.dp))
                    }
                    DropdownMenuItem(
                        text = { Text(item.label, style = JFFont.sans(15f), color = JF.ink, maxLines = 1) },
                        onClick = {
                            open = false
                            item.onPick()
                        },
                    )
                }
            }
        }
        if (!help.isNullOrEmpty()) Text(help, style = JFFont.mono(11f), color = JF.ink3)
    }
}

/** A switch with a title and a line of help. */
@Composable
fun ToggleRow(title: String, on: Boolean, onChange: (Boolean) -> Unit, help: String? = null) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = JFFont.sans(15f, JFFont.Weight.Medium), color = JF.ink)
            if (help != null) Fine(help)
        }
        Switch(
            checked = on,
            onCheckedChange = onChange,
            colors = SwitchDefaults.colors(
                checkedTrackColor = JF.accent,
                checkedThumbColor = JF.panel,
                uncheckedTrackColor = JF.panel2,
                uncheckedThumbColor = JF.ink3,
                uncheckedBorderColor = JF.line,
            ),
        )
    }
}

/** A caption over a date, optional: "today" until one is chosen. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DateField(label: String, date: LocalDate?, onChange: (LocalDate?) -> Unit, help: String? = null) {
    var picking by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = JFFont.mono(11f), color = JF.ink3)
        Row(
            Modifier
                .fillMaxWidth()
                .heightIn(min = 42.dp)
                .background(JF.panel2)
                .border(1.dp, JF.line, RectangleShape)
                .clickable { picking = true }
                .padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(date?.toString() ?: "Pick a date", style = if (date != null) JFFont.mono(15f) else JFFont.sans(15f), color = JF.ink, modifier = Modifier.weight(1f))
            if (date != null) LinkText("Clear", { onChange(null) })
        }
        if (!help.isNullOrEmpty()) Text(help, style = JFFont.mono(11f), color = JF.ink3)
    }
    if (picking) {
        val state = rememberDatePickerState(initialSelectedDateMillis = (date ?: LocalDate.now()).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli())
        DatePickerDialog(
            onDismissRequest = { picking = false },
            confirmButton = {
                TextButton(onClick = {
                    picking = false
                    state.selectedDateMillis?.let { onChange(Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate()) }
                }) { Text("Done", style = JFFont.sans(15f, JFFont.Weight.Semibold), color = JF.accentText) }
            },
            dismissButton = { TextButton(onClick = { picking = false }) { Text("Cancel", style = JFFont.sans(15f), color = JF.ink) } },
        ) { DatePicker(state = state) }
    }
}

/** Numbers as typed by a person: "$1,234.50", "6.125%", " 30000 ". */
object Parse {
    private val noise = Regex("[$,%\\s]")

    fun number(raw: String): Double? {
        val cleaned = raw.replace(noise, "")
        if (cleaned.isEmpty()) return null
        return cleaned.toDoubleOrNull()
    }

    fun clean(raw: String): String = raw.replace(noise, "")
}

/** A destructive action behind a confirmation, as the dashboard's drawers ask. */
@Composable
fun DangerButton(title: String, question: String, message: String, confirm: String, action: suspend () -> Unit) {
    val scope = rememberCoroutineScope()
    var asking by remember { mutableStateOf(false) }
    var working by remember { mutableStateOf(false) }
    QuietButton(if (working) "$title…" else title, { if (!working) asking = true }, destructive = true)
    if (asking) {
        AlertDialog(
            onDismissRequest = { asking = false },
            shape = RoundedCornerShape(4.dp),
            containerColor = JF.panel,
            title = { Text(question, style = JFFont.sans(17f, JFFont.Weight.Semibold), color = JF.ink) },
            text = { Text(message, style = JFFont.sans(14f), color = JF.ink2) },
            confirmButton = {
                TextButton(onClick = {
                    asking = false
                    scope.launch {
                        working = true
                        try { action() } finally { working = false }
                    }
                }) { Text(confirm, style = JFFont.sans(15f, JFFont.Weight.Semibold), color = JF.neg) }
            },
            dismissButton = { TextButton(onClick = { asking = false }) { Text("Cancel", style = JFFont.sans(15f), color = JF.ink) } },
        )
    }
}

/** A small quiet button for a row's actions. */
@Composable
fun SmallButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, destructive: Boolean = false, primary: Boolean = false, enabled: Boolean = true) {
    Box(
        modifier
            .height(30.dp)
            .background(if (primary) JF.accent else JF.panel)
            .border(1.dp, if (primary) JF.accent else JF.line, RectangleShape)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text,
            style = JFFont.mono(12f, JFFont.Weight.Medium),
            color = if (!enabled) JF.ink3 else if (primary) JF.accentInk else if (destructive) JF.neg else JF.ink,
            maxLines = 1,
        )
    }
}

/** The bar's text action (Edit), in the glass of the back button. */
@Composable
fun GlassPill(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, working: Boolean = false) {
    Box(
        modifier
            .height(44.dp)
            .glass(CircleShape)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 16.dp),
        contentAlignment = Alignment.Center,
    ) {
        if (working) {
            CircularProgressIndicator(Modifier.size(18.dp), color = JF.ink3, strokeWidth = 2.dp)
        } else {
            Text(text, style = JFFont.sans(16f, JFFont.Weight.Medium), color = JF.accentText, maxLines = 1)
        }
    }
}

/** A short confirmation that something happened, at the bottom of the screen (the model shows it). */
@Composable
fun ToastHost(text: String?, modifier: Modifier = Modifier) {
    if (text != null) {
        Box(
            modifier
                .background(JF.ink)
                .border(1.dp, JF.lineStrong, RectangleShape)
                .padding(horizontal = 14.dp, vertical = 10.dp),
        ) {
            Text(text, style = JFFont.mono(12f, JFFont.Weight.Medium), color = JF.accentInk, maxLines = 2)
        }
    }
}

@Composable
fun Gap(height: Int) = Spacer(Modifier.height(height.dp))
