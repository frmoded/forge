from forge.sdk import Forge

VAULT = "/Users/odedfuhrmann/projects/obsidian_sandbox/sandbox"


def main():
  client = Forge()

  client.connect(VAULT)

  # Execute a data note — returns its YAML properties
  # data_result = client.execute("hello_forge")
  # print("data:", data_result)

  # Execute an action note — runs its Python facet, captures stdout
  action_result = client.execute("hello_world")
  # action_result = client.execute("hello_forge", x=10, y=5)
  print("action result:", action_result["result"])
  print("captured stdout:", action_result["stdout"])


if __name__ == "__main__":
  main()
