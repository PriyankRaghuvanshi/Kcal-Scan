import React from "react";
import { View, Text, TouchableOpacity, StyleSheet } from "react-native";

export class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      message: "",
    };
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      message: String(error?.message || error || "Unexpected startup error"),
    };
  }

  componentDidCatch(error, info) {
    try {
      // eslint-disable-next-line no-console
      console.log("[AppErrorBoundary]", {
        message: String(error?.message || error || ""),
        stack: String(info?.componentStack || "").slice(0, 2000),
      });
    } catch {}
  }

  onRetry = () => {
    this.setState({ hasError: false, message: "" });
  };

  render() {
    if (this.state.hasError) {
      return (
        <View style={styles.container}>
          <Text style={styles.title}>CalorieClick AI</Text>
          <Text style={styles.subtitle}>We hit a startup issue.</Text>
          <Text style={styles.body} numberOfLines={4}>{this.state.message}</Text>
          <TouchableOpacity style={styles.btn} onPress={this.onRetry}>
            <Text style={styles.btnText}>Try again</Text>
          </TouchableOpacity>
        </View>
      );
    }
    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0b1220",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
  },
  title: { color: "#fff", fontSize: 24, fontWeight: "800" },
  subtitle: { color: "#cfe3ff", fontSize: 14, marginTop: 10 },
  body: { color: "#9ab0cf", fontSize: 12, marginTop: 8, textAlign: "center" },
  btn: {
    marginTop: 16,
    backgroundColor: "#132033",
    borderColor: "#2a3d5b",
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  btnText: { color: "#e7f0ff", fontSize: 13, fontWeight: "700" },
});

export default AppErrorBoundary;
