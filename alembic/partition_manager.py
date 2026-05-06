"""
Partition Management Script for ledger_entry table
Location: app/migrations/partition_manager.py

Gère automatiquement la création des partitions mensuelles
"""

from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()


class LedgerPartitionManager:
    """
    Gère les partitions du ledger_entry par date
    À lancer: monthly via cron ou scheduler
    """

    def __init__(self, database_url: str = None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        self.engine = create_engine(self.database_url)
        self.Session = sessionmaker(bind=self.engine)

    def ensure_future_partitions(self, months_ahead: int = 6):
        """
        S'assure que les partitions existent pour les N prochains mois
        
        Args:
            months_ahead: Nombre de mois à l'avance pour créer les partitions
        """
        today = datetime.utcnow()
        
        with self.Session() as session:
            for i in range(months_ahead):
                current_date = today + timedelta(days=30*i)
                year = current_date.year
                month = current_date.month
                
                next_month = current_date + timedelta(days=30)
                
                partition_name = f"ledger_entry_{year}_{month:02d}"
                start_date = current_date.replace(day=1)
                end_date = next_month.replace(day=1)
                
                try:
                    # Vérifier si la partition existe déjà
                    result = session.execute(
                        text(f"""
                            SELECT EXISTS(
                                SELECT 1 FROM pg_tables 
                                WHERE tablename = '{partition_name}'
                            )
                        """)
                    ).scalar()
                    
                    if not result:
                        # Créer la partition
                        sql = f"""
                            CREATE TABLE {partition_name} PARTITION OF ledger_entry
                            FOR VALUES FROM ('{start_date.isoformat()}') TO ('{end_date.isoformat()}');
                        """
                        session.execute(text(sql))
                        session.commit()
                        print(f"✓ Created partition {partition_name}")
                    else:
                        print(f"✓ Partition {partition_name} already exists")
                except Exception as e:
                    session.rollback()
                    print(f"✗ Error creating partition {partition_name}: {e}")

    def create_indexes_on_partitions(self, partition_name: str):
        """
        Crée les indexes sur une partition spécifique
        """
        indexes = [
            f"CREATE INDEX IF NOT EXISTS idx_{partition_name}_merchant_id ON {partition_name}(merchant_id)",
            f"CREATE INDEX IF NOT EXISTS idx_{partition_name}_type ON {partition_name}(type)",
            f"CREATE INDEX IF NOT EXISTS idx_{partition_name}_status ON {partition_name}(status)",
            f"CREATE INDEX IF NOT EXISTS idx_{partition_name}_created_at ON {partition_name}(created_at)",
        ]
        
        with self.Session() as session:
            for idx_sql in indexes:
                try:
                    session.execute(text(idx_sql))
                    session.commit()
                    print(f"✓ Created index: {idx_sql}")
                except Exception as e:
                    session.rollback()
                    print(f"✗ Error creating index: {e}")

    def cleanup_old_partitions(self, keep_months: int = 24):
        """
        Supprime les anciennes partitions (garder les 24 derniers mois)
        À lancer: yearly
        
        Args:
            keep_months: Nombre de mois à conserver
        """
        cutoff_date = datetime.utcnow() - timedelta(days=30*keep_months)
        cutoff_year = cutoff_date.year
        cutoff_month = cutoff_date.month
        
        with self.Session() as session:
            # Récupérer toutes les partitions
            result = session.execute(
                text("""
                    SELECT tablename FROM pg_tables 
                    WHERE tablename LIKE 'ledger_entry_%'
                    ORDER BY tablename
                """)
            ).fetchall()
            
            for (tablename,) in result:
                try:
                    # Extraire année et mois du nom
                    parts = tablename.split('_')
                    if len(parts) >= 4:
                        year = int(parts[2])
                        month = int(parts[3])
                        
                        # Si avant cutoff, supprimer
                        if year < cutoff_year or (year == cutoff_year and month < cutoff_month):
                            session.execute(text(f"DROP TABLE IF EXISTS {tablename}"))
                            session.commit()
                            print(f"✓ Dropped old partition {tablename}")
                except Exception as e:
                    session.rollback()
                    print(f"✗ Error dropping partition {tablename}: {e}")


# ========== USAGE ==========

if __name__ == '__main__':
    manager = LedgerPartitionManager()
    
    # Créer les partitions pour les 6 prochains mois
    print("Creating future partitions...")
    manager.ensure_future_partitions(months_ahead=6)
    
    # Nettoyer les anciennes partitions (garder 24 mois)
    print("\nCleaning up old partitions...")
    manager.cleanup_old_partitions(keep_months=24)
    
    print("\nPartition management complete!")

"""
Ajouter à crontab (VPS):

# Créer les partitions du prochain mois (le 1er de chaque mois)
0 0 1 * * cd /path/to/novasell && python -m app.migrations.partition_manager

# Nettoyer les vieilles partitions (1x par an, le 1er janvier)
0 0 1 1 * cd /path/to/novasell && python -m app.migrations.partition_manager --cleanup
"""
