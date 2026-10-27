FROM openpolicyagent/opa:1.21.4-static
COPY authz.rego /policy/authz.rego
USER 65532:65532
EXPOSE 8181
ENTRYPOINT ["/opa"]
CMD ["run", "--server", "--addr=0.0.0.0:8181", "--disable-telemetry", "/policy/authz.rego"]
