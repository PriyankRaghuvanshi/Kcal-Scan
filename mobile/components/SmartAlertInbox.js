/**
 * SmartAlertInbox - Preview list of smart food alert candidates.
 */

import React from "react";
import { View, Text, FlatList, StyleSheet, TouchableOpacity, ActivityIndicator } from "react-native";
import { SmartAlertCard } from "./SmartAlertCard";

export function SmartAlertInbox({
  candidates = [],
  loading = false,
  onOpenPlace,
  onDismiss,
  onRefresh,
  emptyMessage = "No smart alerts right now. Check back when you have macros left or when you're near food.",
}) {
  const list = Array.isArray(candidates) ? candidates : [];

  function renderItem({ item }) {
    return (
      <SmartAlertCard
        candidate={item}
        onOpen={onOpenPlace}
        onDismiss={onDismiss}
      />
    );
  }

  function ListEmpty() {
    if (loading) {
      return (
        <View style={styles.empty}>
          <ActivityIndicator size="small" color="#2563eb" />
          <Text style={styles.emptyText}>Checking for smart alerts…</Text>
        </View>
      );
    }
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyText}>{emptyMessage}</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={list}
        keyExtractor={(item) => item.place_id + ":" + (item.alert_type || "") + ":" + (item.best_item_name || "")}
        renderItem={renderItem}
        ListEmptyComponent={ListEmpty}
        contentContainerStyle={list.length === 0 ? styles.emptyContainer : styles.listContainer}
        refreshing={loading}
        onRefresh={onRefresh}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    minHeight: 120,
  },
  listContainer: {
    padding: 12,
    paddingBottom: 24,
  },
  emptyContainer: {
    flexGrow: 1,
    padding: 24,
    justifyContent: "center",
  },
  empty: {
    alignItems: "center",
    paddingVertical: 24,
  },
  emptyText: {
    fontSize: 14,
    color: "#64748b",
    textAlign: "center",
    marginTop: 8,
  },
});
