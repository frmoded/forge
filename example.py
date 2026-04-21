from forge.sdk import Forge


def main():
  # Initialize the Forge client
  client = Forge()

  # Verify Phase 1: Ensure the skeleton returns 3
  result = client.test()

  print(f"Forge test result: {result}")


if __name__ == "__main__":
  main()
